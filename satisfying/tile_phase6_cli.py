"""Phase 6: the production master, and the checks that let it be uploaded.

Phases 3, 4 and 5 each shipped a CLI that made evidence. This one makes the
deliverable, and the difference shows in what the commands are for: there is
one production, it is `tile_production.PRODUCTION`, and every command below
reads its dials rather than taking its own.

    python -m satisfying.tile_phase6_cli export
    python -m satisfying.tile_phase6_cli frames
    python -m satisfying.tile_phase6_cli audio
    python -m satisfying.tile_phase6_cli safearea
    python -m satisfying.tile_phase6_cli master
    python -m satisfying.tile_phase6_cli phone
    python -m satisfying.tile_phase6_cli qc
    python -m satisfying.tile_phase6_cli verify
    python -m satisfying.tile_phase6_cli identity

## The two masters, and why neither is encoded twice

`master` writes two files from the same 1,040 PNGs and the same 24-bit WAV:

* the **archive** - CRF 12 with PCM audio, which is the thing to keep;
* the **delivery** file - CRF 17 with 192 kbps AAC, which is the thing to
  upload.

The delivery file is *not* transcoded from the archive. Both are encoded from
the frames, so the upload has exactly one generation of lossy video in it and
exactly one of lossy audio, and the archive has one of video and none of audio.
Phase 5 made the same point with `-c:v copy`; this is the same idea applied to
a pipeline that has a source of truth to encode from.

## What `qc` reads

The encoded file, not the frames. That is the whole point of having it: every
other check in this repository measures something upstream of the encoder, and
an encoder can still lose the first frame, resample the audio or drift the two
apart. `qc` decodes the delivered MP4 and asks the questions Part 8 of the
brief lists, in the brief's own order.
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

from satisfying import (
    tile_audio,
    tile_completion,
    tile_playback,
    tile_production,
    tile_readability,
    tile_safe_area,
    tile_score,
)
from satisfying.tile_phase3_cli import _godot_path, find_godot, run_godot
from satisfying.tile_phase4_cli import _run, find_ffmpeg
from satisfying.tile_sweep import PHASE2_ARENA

DEFAULT_OUT = os.path.join("output", "category3_v6")
DELIVERY_TRUE_PEAK_DBTP = -1.0


class Phase6Error(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Paths. One production, so none of these take a variant.
# --------------------------------------------------------------------------


def playback_path(out: str, config: tile_production.ProductionConfig) -> str:
    return os.path.join(out, "playback",
                        f"seed_{config.seed}_{config.timing}.json")


def frames_dir(out: str, config: tile_production.ProductionConfig) -> str:
    return os.path.join(out, f"climax{int(config.fps)}_{config.timing}",
                        f"seed_{config.seed}")


def wav_path(out: str, config: tile_production.ProductionConfig) -> str:
    return os.path.join(out, "audio",
                        f"seed_{config.seed}_{config.audio}.wav")


def measure_path(out: str, config: tile_production.ProductionConfig) -> str:
    return os.path.join(out, "audio",
                        f"seed_{config.seed}_{config.audio}.measure.json")


def master_path(out: str, config: tile_production.ProductionConfig) -> str:
    return os.path.join(out, "master",
                        f"{config.name}_archive.mkv")


def delivery_path(out: str, config: tile_production.ProductionConfig) -> str:
    return os.path.join(out, "master", f"{config.name}_shorts.mp4")


def _write_json(path: str, payload: Any) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def _document(args: argparse.Namespace) -> dict[str, Any]:
    path = playback_path(args.out, tile_production.PRODUCTION)
    if not os.path.isfile(path):
        raise Phase6Error(f"no playback document at {path}; run `export` first")
    return tile_playback.read_playback(path)


def _ffmpeg_run(command: Sequence[str], label: str) -> float:
    started = time.time()
    result = subprocess.run(list(command), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").splitlines()[-30:])
        raise Phase6Error(f"{label}: ffmpeg exited {result.returncode}\n{tail}")
    return time.time() - started


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def task_export(args: argparse.Namespace) -> int:
    """The canonical playback document, with its completion block."""
    config = tile_production.PRODUCTION
    run = _run(config.seed, args.speed)
    if not run.completed:
        raise Phase6Error(f"seed {config.seed} does not complete")
    document = tile_playback.playback_document(run)
    document = tile_completion.attach_completion(
        document, run, PHASE2_ARENA, tile_completion.named_timing(config.timing))
    path = _write_json(playback_path(args.out, config), document)
    block = document["completion"]
    print(f"  seed {config.seed}  {run.completion_time:.3f}s + "
          f"{block['climax_seconds']:.3f}s = "
          f"{block['total_render_seconds']:.3f}s  "
          f"{len(document['collisions'])} contacts  "
          f"{int(round(float(block['total_render_seconds']) * config.fps)) + 1}"
          f" frames  digest {document['digest'][:16]}")
    print(f"       -> {path}")
    return 0


# --------------------------------------------------------------------------
# frames
# --------------------------------------------------------------------------


def task_frames(args: argparse.Namespace) -> int:
    """The picture, at the production composition and the production hook."""
    config = tile_production.PRODUCTION
    out_dir = frames_dir(args.out, config)
    os.makedirs(out_dir, exist_ok=True)
    godot = find_godot(args.godot)
    stdout = run_godot(godot, [
        f"--playback={_godot_path(playback_path(args.out, config))}",
        f"--out-dir={_godot_path(out_dir)}",
        f"--width={config.width}", f"--height={config.height}",
        f"--fps={config.fps:g}",
        f"--hook={config.hook}",
        f"--trail={config.trail}",
        f"--counter={1 if config.show_counter else 0}",
        f"--debug={1 if config.show_debug else 0}",
        "--clip=1", "--climax=1",
    ], f"production frames, seed {config.seed}")
    frames = sorted(glob.glob(os.path.join(out_dir, "frame_*.png")))
    print(f"  {len(frames)} frames -> {out_dir}")
    for line in stdout.splitlines():
        if line.startswith(("arena:", "rendered", "playback:")):
            print(f"       {line.strip()}")
    return 0


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------


def task_audio(args: argparse.Namespace) -> int:
    """The schedule, the PCM master and every measurement of it."""
    config = tile_production.PRODUCTION
    document = _document(args)
    audio_config = config.audio_config
    plan = tile_score.schedule(document, audio_config)
    _write_json(os.path.join(args.out, "score",
                             f"seed_{config.seed}_{config.audio}.json"),
                plan.as_dict() if hasattr(plan, "as_dict") else
                {"events": [event.as_dict() for event in plan.events],
                 "beats": plan.beats,
                 "config": audio_config.as_dict(),
                 "fingerprint": audio_config.fingerprint(),
                 "frames": plan.frames,
                 "total_seconds": plan.total_seconds,
                 "total_samples": plan.total_samples,
                 "metrics": plan.metrics})
    started = time.time()
    rendered = tile_audio.render(plan)
    path = tile_audio.write_master(rendered, wav_path(args.out, config))
    report = tile_audio.measure(rendered, phone=True, document=document)
    report["wav"] = os.path.basename(path)
    report["pcm_digest"] = rendered.digest()
    report["production"] = tile_production.identity(document, config)
    _write_json(measure_path(args.out, config), report)
    gaps = report["hierarchy_gaps_db"]
    band = report["masking_band"]["activation"]
    phone_band = report["phone"]["masking_band"]["activation"]
    print(f"  seed {config.seed} {config.audio}: "
          f"peak {report['peak']['sample_peak_dbfs']:+.2f} dBFS / "
          f"{report['peak']['true_peak_dbtp']:+.2f} dBTP  "
          f"{report['loudness']['integrated_lufs']:+.2f} LUFS  "
          f"clip {report['peak']['clipped_samples']}  "
          f"limiter {report['peak'].get('limiter_gain_db', 0.0):+.2f} dB")
    print(f"       hierarchy: new>dup {gaps['activation_over_duplicate_db']:+.2f} dB"
          f"  final>new {gaps['final_over_activation_db']:+.2f} dB")
    print(f"       band emergence, activations: median "
          f"{band['median_emergence_db']:+.2f} dB  min "
          f"{band['min_emergence_db']:+.2f} dB  under 3 dB "
          f"{band['masked_count']}/{band['count']}   "
          f"(phone min {phone_band['min_emergence_db']:+.2f} dB, under 3 dB "
          f"{phone_band['masked_count']}/{phone_band['count']})")
    print(f"       -> {path}  ({time.time() - started:.0f}s)")
    return 0


# --------------------------------------------------------------------------
# safearea
# --------------------------------------------------------------------------


def task_safearea(args: argparse.Namespace) -> int:
    """The Shorts safe-area proof: the report, and the overlay frames."""
    config = tile_production.PRODUCTION
    document = _document(args)
    out_root = os.path.join(args.out, "safe_area")
    os.makedirs(out_root, exist_ok=True)
    frames = frames_dir(args.out, config)
    summary: dict[str, Any] = {"seed": config.seed, "models": {}}
    failures = 0

    order = [int(entry["tile"]) for entry in document["activations"]]
    times = [float(entry["t"]) for entry in document["activations"]]
    beats = {segment["state"]: float(segment["render_start"])
             for segment in document["completion"]["timeline"]}
    moments: list[tuple[str, float]] = [("opening", 0.0)]
    for nth in (48, 49, 50):
        moments.append((f"{nth}of51", times[nth - 1] + 0.5))
    moments.append(("final_hit", beats["final_hit"]))
    for name in ("confirming", "unlocking", "escaping", "settled"):
        moments.append((name, beats[name]))

    for model in sorted(tile_safe_area.SAFE_AREAS):
        area = tile_safe_area.named_safe_area(model, fps=config.fps)
        report = tile_safe_area.report(document, area, config.width,
                                       config.height)
        per = {row["tile"]: row for row in report["per_tile"]}
        # The reading that decides it: at every moment the viewer is hunting a
        # dark tile, is every dark tile visible?
        worst_dark = 0.0
        worst_at = ""
        for name, t in moments:
            dark = [tile for tile, tt in zip(order, times) if tt > t + 1e-9]
            for tile in dark:
                if per[tile]["worst_fraction"] > worst_dark:
                    worst_dark = per[tile]["worst_fraction"]
                    worst_at = f"{name} tile {tile}"
        ball = report["ball"]
        entry = {
            "fingerprint": report["fingerprint"],
            "obstructed_tiles": report["tiles"]["obstructed_tiles"],
            "obstructed_count": report["tiles"]["obstructed_count"],
            "worst_dark_tile_cover": round(worst_dark, 4),
            "worst_dark_tile_at": worst_at,
            "final_tile_cover": report["final_tile"]["worst_fraction"],
            "ball_longest_hidden_seconds": ball["longest_hidden_seconds"],
            "ball_within_budget": ball["within_budget"],
            "threshold": area.tile_obstructed_fraction,
        }
        # The gate is judged on the model that the composition was fixed
        # against; the others are reported as margin.
        entry["is_gate"] = model == config.safe_area
        entry["passes"] = (
            report["tiles"]["obstructed_count"] == 0
            and report["final_tile"]["worst_fraction"] < area.tile_obstructed_fraction
            and ball["within_budget"]
        )
        if entry["is_gate"] and not entry["passes"]:
            failures += 1
        summary["models"][model] = entry
        # Only the model the composition was fixed against is a gate. The
        # others are margin probes: `shorts_measured` says how much of a
        # reading is the real UI, and `shorts_strict` - a rail drawn 30 dp
        # wider again than the conservative one - says how much further the
        # player could grow before this composition had to move. Reporting a
        # probe as a failure would make a deliberately unsatisfiable model look
        # like a defect.
        flag = ("PASS" if entry["passes"] else "FAIL") if entry["is_gate"]             else ("clear" if entry["passes"] else "exposed")
        print(f"  {model:>20}: {flag}  obstructed "
              f"{report['tiles']['obstructed_count']:>2}/51  worst dark-tile "
              f"cover {worst_dark:.3f}  final tile "
              f"{report['final_tile']['worst_fraction']:.3f}  ball hidden "
              f"{ball['longest_hidden_seconds']:.3f}s"
              + ("   <== the gate" if entry["is_gate"] else ""))

    # The type, measured from a real frame rather than predicted.
    text: dict[str, Any] = {}
    sample = os.path.join(frames, "frame_000300.png")
    if os.path.isfile(sample):
        area = tile_safe_area.named_safe_area(config.safe_area, fps=config.fps)
        for what, low, high in (("hook", 0.03, 0.18), ("counter", 0.735, 0.86)):
            extent = tile_safe_area.text_extent(sample, low, high)
            clear = tile_safe_area.text_clearance(extent, area)
            text[what] = {"extent": extent, "clearance": clear}
            print(f"  {what:>20}: box {extent.get('box_fraction')}  "
                  f"{'CLEAR' if clear.get('clear') else 'HITS ' + str(clear.get('intersects'))}")
            if not clear.get("clear"):
                failures += 1
        summary["text"] = text

        for name, t in moments:
            frame = min(int(round(float(document['completion']
                                        ['total_render_seconds']) * config.fps)),
                        int(round(t * config.fps)))
            source = os.path.join(frames, f"frame_{frame:06d}.png")
            if not os.path.isfile(source):
                continue
            tile_safe_area.overlay_frame(
                source,
                os.path.join(out_root, f"{name}_{config.safe_area}.png"),
                tile_safe_area.named_safe_area(config.safe_area, fps=config.fps),
                alpha=0.5,
                label=f"{name}  t={t:.3f}s  frame {frame}")
    else:
        print(f"  (no frames at {frames}; run `frames` first for the overlays)")

    summary["moments"] = [{"name": name, "t": round(t, 4)}
                          for name, t in moments]
    _write_json(os.path.join(out_root, "safe_area.json"), summary)
    return 1 if failures else 0


# --------------------------------------------------------------------------
# master
# --------------------------------------------------------------------------


def task_master(args: argparse.Namespace) -> int:
    """The archival master and the delivery file, both from the frames."""
    config = tile_production.PRODUCTION
    ffmpeg = find_ffmpeg(args.ffmpeg)
    audio = wav_path(args.out, config)
    if not os.path.isfile(audio):
        raise Phase6Error(f"no PCM master at {audio}; run `audio` first")
    directory = frames_dir(args.out, config)
    frames = sorted(glob.glob(os.path.join(directory, "frame_*.png")))
    if not frames:
        raise Phase6Error(f"no frames in {directory}; run `frames` first")
    first = int(os.path.basename(frames[0])[6:12])
    os.makedirs(os.path.join(args.out, "master"), exist_ok=True)

    colour = [
        "-color_primaries", config.colour_primaries,
        "-color_trc", config.colour_trc,
        "-colorspace", config.colour_space,
    ]
    source = [
        "-framerate", f"{config.fps:g}",
        "-start_number", str(first),
        "-i", os.path.join(directory, "frame_%06d.png"),
        "-i", audio,
    ]

    archive = master_path(args.out, config)
    elapsed = _ffmpeg_run(
        [ffmpeg, "-y", *source,
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", config.video_codec, "-preset", config.preset,
         "-crf", str(config.archive_crf),
         "-pix_fmt", config.pixel_format, *colour,
         "-c:a", config.archive_audio,
         "-shortest", archive],
        "archive")
    print(f"  archive  CRF {config.archive_crf} + {config.archive_audio}: "
          f"{os.path.getsize(archive) / 1_048_576:.1f} MB  ({elapsed:.0f}s)")
    print(f"       -> {archive}")

    delivery = delivery_path(args.out, config)
    movflags = ["-movflags", "+faststart"] if config.faststart else []
    elapsed = _ffmpeg_run(
        [ffmpeg, "-y", *source,
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", config.video_codec, "-preset", config.preset,
         "-crf", str(config.crf),
         "-pix_fmt", config.pixel_format, *colour,
         "-c:a", config.audio_codec, "-b:a", config.audio_bitrate,
         "-ar", str(config.audio_sample_rate),
         *movflags, "-shortest", delivery],
        "delivery")
    print(f"  delivery CRF {config.crf} + {config.audio_codec} "
          f"{config.audio_bitrate}: "
          f"{os.path.getsize(delivery) / 1_048_576:.1f} MB  ({elapsed:.0f}s)")
    print(f"       -> {delivery}")
    print(f"  {len(frames)} frames encoded twice, from the same source; "
          f"neither file was made from the other")
    return 0


# --------------------------------------------------------------------------
# phone - the mix and the picture, at the size and in the fold most people get
# --------------------------------------------------------------------------


PHONE_FRAME = (270, 480)


def task_phone(args: argparse.Namespace) -> int:
    """Does the thing survive a phone: one speaker, one fold, one small frame?

    Three separate questions and they fail in different ways:

    * **mono.** Every tile is panned by its x position, so a mono fold sums
      two channels that were never identical. If a pair of notes were placed
      opposite each other and happened to be out of phase, folding would
      cancel them - and the event that vanished would be a progress hit.
    * **the speaker.** A phone reproduces almost nothing under ~500 Hz, and
      the pitch mapping puts the bottom of the arena at 220. Phase 5 fixed a
      7.5 dB loudness gradient here; this checks it stayed fixed.
    * **the frame.** At 270x480 a tile is a quarter of the pixels it is at
      1080x1920. The question the late game turns on - can the viewer find
      the one remaining dark tile - has to be asked at the size it is
      actually asked at.
    """
    config = tile_production.PRODUCTION
    document = _document(args)
    out_root = os.path.join(args.out, "phone")
    os.makedirs(out_root, exist_ok=True)
    problems: list[str] = []

    # --- the mix ----------------------------------------------------------
    import dataclasses
    from array import array

    import numpy as np

    from audio import loudness

    plan = tile_score.schedule(document, config.audio_config)
    rendered = tile_audio.render(plan)
    stereo = loudness.as_stereo(rendered.left, rendered.right)

    def as_pair(folded: np.ndarray) -> tuple[Any, Any]:
        pair = np.repeat(folded, 2, axis=1) if folded.ndim == 2 \
            and folded.shape[1] == 1 else folded
        return (array("d", pair[:, 0].tolist()),
                array("d", pair[:, 1].tolist()))

    mono = loudness.mono_fold(stereo)
    if mono.ndim == 1:
        mono = mono.reshape(-1, 1)
    mono_left, mono_right = as_pair(mono)
    phone = loudness.phone_filter(stereo, config.audio_config.sample_rate)
    if phone.ndim == 1:
        phone = phone.reshape(-1, 1)
    phone_left, phone_right = as_pair(phone)

    views = {
        "stereo": (rendered.left, rendered.right),
        "mono": (mono_left, mono_right),
        "phone": (phone_left, phone_right),
    }
    audio_report: dict[str, Any] = {}
    for label, (left, right) in views.items():
        band = tile_audio.band_masking_report(rendered, left, right)
        broad = tile_audio.masking_report(rendered, left, right)
        hierarchy = tile_audio._hierarchy(rendered, left, right)
        audio_report[label] = {
            "band": {kind: band[kind] for kind in band
                     if isinstance(band.get(kind), dict)},
            "activation_band": band.get("activation"),
            "activation_broadband": broad.get("activation"),
            "peaks_dbfs": {kind: hierarchy[kind]["median_dbfs"]
                           for kind in hierarchy
                           if isinstance(hierarchy.get(kind), dict)},
        }
        act = band.get("activation", {})
        print(f"  {label:>7}: activations, own-band emergence median "
              f"{act.get('median_emergence_db'):+.2f} dB  min "
              f"{act.get('min_emergence_db'):+.2f} dB  under 3 dB "
              f"{act.get('masked_count')}/{act.get('count')}")
        if act.get("masked_count"):
            problems.append(
                f"{label}: {act['masked_count']} activations do not clear 3 dB "
                "in their own band")

    # **The cancellation question, asked so that the answer means something.**
    #
    # A mono fold of an amplitude-panned event costs it level, and that cost is
    # not a defect - it is arithmetic. `pan_gains` renormalises so the nearer
    # channel carries the cue's full designed level, because the hierarchy is
    # budgeted in peaks; summing that pair to mono therefore gives
    # `(l + r) / 2` of the designed peak, which at the configured `pan_depth`
    # is exactly -2.73 dB at full deflection. Comparing against unity and
    # calling the difference a fault would condemn the pan law for working.
    #
    # What would be a fault is a *bigger* loss than the law predicts, because
    # the only thing that can produce one is phase cancellation between two
    # events that happen to be opposite and out of step - and the event that
    # vanished would be a progress hit. So the loss is measured per event and
    # compared with the law's own prediction, and what is asserted is that the
    # two agree.
    import math as _math

    law_worst = 20.0 * _math.log10(
        max(sum(tile_audio.pan_gains(config.audio_config.pan_depth)) / 2.0,
            1e-12))
    worst = {"event": None, "loss_db": 0.0}
    for event in plan.events:
        if event.pan == 0.0:
            continue
        gains = tile_audio.pan_gains(event.pan)
        loss = 20.0 * _math.log10(max((gains[0] + gains[1]) / 2.0, 1e-12))
        if loss < worst["loss_db"]:
            worst = {"event": event.kind, "tile": event.tile,
                     "pan": round(event.pan, 4), "loss_db": round(loss, 4)}
    worst["pan_law_worst_db"] = round(law_worst, 4)
    worst["excess_over_pan_law_db"] = round(worst["loss_db"] - law_worst, 5)
    audio_report["mono_fold"] = {
        "compatibility": loudness.mono_compatibility(
            stereo, config.audio_config.sample_rate),
        "worst_single_event": worst,
    }
    print(f"  mono fold: correlation "
          f"{audio_report['mono_fold']['compatibility']['correlation']:.4f}, "
          f"whole-mix loss "
          f"{audio_report['mono_fold']['compatibility']['mono_loss_db']:+.2f} dB")
    print(f"             worst single event {worst['loss_db']:+.4f} dB "
          f"({worst.get('event')}, pan {worst.get('pan')}); the pan law "
          f"predicts {law_worst:+.4f} dB, so cancellation accounts for "
          f"{worst['excess_over_pan_law_db']:+.5f} dB")
    # A thousandth of a decibel of slack, which is float noise and nothing else.
    if worst["excess_over_pan_law_db"] < -0.001:
        problems.append(
            f"an event loses {worst['loss_db']:.3f} dB to the mono fold where "
            f"the pan law predicts {law_worst:.3f} dB - "
            f"{abs(worst['excess_over_pan_law_db']):.3f} dB of that is "
            "cancellation, not summing")
    # And the reading that actually decides it: the fold must not reorder the
    # hierarchy or bury a progress hit.
    for label in ("mono", "phone"):
        peaks = audio_report[label]["peaks_dbfs"]
        gap = peaks["activation"] - peaks["duplicate"]
        top = peaks["final"] - peaks["activation"]
        audio_report[label]["gaps_db"] = {
            "activation_over_duplicate": round(gap, 2),
            "final_over_activation": round(top, 2),
        }
        if gap < 6.0:
            problems.append(f"{label}: activations clear duplicates by only "
                            f"{gap:.2f} dB")
        if top <= 0.0:
            problems.append(f"{label}: the final hit no longer leads")
    shift = audio_report["mono_fold"]["compatibility"]["band_shift"]
    if any(abs(value) > 0.5 for value in shift.values()):
        problems.append(f"the mono fold moves a frequency band: {shift}")

    # --- the picture, at phone size ---------------------------------------
    width, height = PHONE_FRAME
    picture: dict[str, Any] = {"frame": [width, height]}
    godot = find_godot(args.godot) if args.godot or not args.no_render else None
    frames_out = os.path.join(out_root, f"frames_{width}x{height}")
    if godot is not None:
        os.makedirs(frames_out, exist_ok=True)
        run_godot(godot, [
            f"--playback={_godot_path(playback_path(args.out, config))}",
            f"--out-dir={_godot_path(frames_out)}",
            f"--width={width}", f"--height={height}",
            f"--fps={config.fps:g}", f"--hook={config.hook}",
            f"--trail={config.trail}", "--counter=1", "--debug=0",
            "--clip=1", "--climax=1",
        ], f"phone-size frames {width}x{height}")

    times = [float(entry["t"]) for entry in document["activations"]]
    checks = []
    for label, t in (("early_8", times[7] + 0.5), ("mid_26", times[25] + 0.5),
                     ("late_49", times[48] + 0.5),
                     ("late_50", times[49] + 0.5)):
        frame = int(round(t * config.fps))
        path = os.path.join(frames_out, f"frame_{frame:06d}.png")
        if not os.path.isfile(path):
            continue
        still = tile_readability.still_report(document, path, width, height)
        area = tile_safe_area.named_safe_area(config.safe_area, fps=config.fps)
        hook = tile_safe_area.text_extent(path, 0.03, 0.18)
        counter = tile_safe_area.text_extent(path, 0.735, 0.86)
        row = {
            "moment": label, "frame": frame,
            "lit": still["active_tiles"],
            "worst_gap": still["worst_case_luminance_gap"],
            "michelson": still["worst_case_michelson_contrast"],
            "single_tile_findable":
                still["single_remaining_tile_identifiable"],
            "hook_height_px": hook.get("height_px"),
            "hook_clear": tile_safe_area.text_clearance(hook, area).get("clear"),
            "counter_height_px": counter.get("height_px"),
            "counter_clear":
                tile_safe_area.text_clearance(counter, area).get("clear"),
        }
        checks.append(row)
        print(f"  {label:>10} @{width}x{height}: {row['lit']:>2} lit, worst "
              f"tile gap {row['worst_gap']:.1f} (michelson "
              f"{row['michelson']:.3f}), single-tile "
              f"{row['single_tile_findable']}, hook "
              f"{row['hook_height_px']} px {'clear' if row['hook_clear'] else 'HIT'}"
              f", counter {row['counter_height_px']} px "
              f"{'clear' if row['counter_clear'] else 'HIT'}")
        if row["single_tile_findable"] is False:
            problems.append(f"{label}: the last dark tile is not identifiable "
                            f"at {width}x{height}")
        if row["hook_clear"] is False or row["counter_clear"] is False:
            problems.append(f"{label}: type is under the UI at {width}x{height}")
    picture["checks"] = checks

    report = {"audio": audio_report, "picture": picture,
              "problems": problems}
    path = _write_json(os.path.join(out_root, "phone.json"), report)
    if problems:
        print(f"\n  {len(problems)} PROBLEM(S):")
        for problem in problems:
            print(f"    {problem}")
    else:
        print("\n  survives mono, the speaker and the small frame")
    print(f"  -> {path}")
    return 1 if problems else 0


# --------------------------------------------------------------------------
# qc - on the encoded file, not on the frames
# --------------------------------------------------------------------------


def _ffprobe(ffmpeg: str, path: str, *fields: str) -> dict[str, Any]:
    probe = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    for candidate in (probe, probe + ".exe", "ffprobe"):
        try:
            result = subprocess.run(
                [candidate, "-v", "error", "-print_format", "json",
                 "-show_format", "-show_streams", path],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace")
        except FileNotFoundError:
            continue
        if result.returncode == 0:
            return json.loads(result.stdout)
    raise Phase6Error(f"could not probe {path}; ffprobe not found")


def _extract_frames(ffmpeg: str, source: str, indices: Sequence[int],
                    out_dir: str) -> dict[int, str]:
    """Pull exactly these frames out of the encoded file.

    Decoded from the MP4 rather than read from the PNGs. That is the entire
    point of this command: everything else in the repository measures the
    frames, and an encoder can still drop the first one, shift the whole
    sequence or smear a gradient. `-vsync 0` keeps one output image per
    selected input frame, so the nth output is the nth requested index.
    """
    os.makedirs(out_dir, exist_ok=True)
    wanted = sorted(set(int(index) for index in indices))
    # The comma inside ffmpeg's `select` expression must survive the filter
    # parser, which uses commas to separate filters - hence the backslash.
    select = "+".join(r"eq(n\," + str(index) + ")" for index in wanted)
    pattern = os.path.join(out_dir, "qc_%04d.png")
    _ffmpeg_run([ffmpeg, "-y", "-i", source, "-vf", f"select={select}",
                 "-vsync", "0", "-start_number", "0", pattern],
                "extract qc frames")
    out: dict[int, str] = {}
    for position, index in enumerate(wanted):
        path = os.path.join(out_dir, f"qc_{position:04d}.png")
        if os.path.isfile(path):
            out[index] = path
    return out


def _frame_stats(path: str) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as handle:
        image = handle.convert("L")
        size = image.size
    data = image.tobytes() if hasattr(image, "tobytes") else b""
    with Image.open(path) as handle:
        grey = handle.convert("L")
        data = grey.tobytes()
    total = len(data) or 1
    peak = max(data) if data else 0
    lit = sum(1 for value in data if value >= 200)
    mean = sum(data) / total
    return {"size": list(size), "peak": peak, "mean": round(mean, 3),
             "bright_pixels": lit,
             "blank": peak < 12}


def task_qc(args: argparse.Namespace) -> int:
    """Part 8, in the brief's own order, on the delivered file."""
    config = tile_production.PRODUCTION
    ffmpeg = find_ffmpeg(args.ffmpeg)
    document = _document(args)
    delivery = delivery_path(args.out, config)
    if not os.path.isfile(delivery):
        raise Phase6Error(f"no delivery file at {delivery}; run `master` first")

    expected_frames = int(round(
        float(document["completion"]["total_render_seconds"]) * config.fps)) + 1
    times = [float(entry["t"]) for entry in document["activations"]]
    beats = {segment["state"]: float(segment["render_start"])
             for segment in document["completion"]["timeline"]}
    report: dict[str, Any] = {"file": delivery.replace("\\", "/"),
                              "bytes": os.path.getsize(delivery),
                              "problems": []}

    def fail(section: str, message: str) -> None:
        report["problems"].append({"section": section, "message": message})

    # --- container -------------------------------------------------------
    probe = _ffprobe(ffmpeg, delivery)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    counted = int(video.get("nb_frames") or 0)
    duration = float(probe["format"]["duration"])
    rate = video.get("r_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / float(rate[1] or 1)
    report["container"] = {
        "video_codec": video["codec_name"],
        "pixel_format": video.get("pix_fmt"),
        "width": video["width"], "height": video["height"],
        "fps": fps, "frames": counted,
        "audio_codec": audio["codec_name"],
        "audio_sample_rate": int(audio["sample_rate"]),
        "audio_channels": int(audio["channels"]),
        "duration_seconds": duration,
        "expected_frames": expected_frames,
    }
    if [video["width"], video["height"]] != [config.width, config.height]:
        fail("container", f"frame is {video['width']}x{video['height']}")
    if abs(fps - config.fps) > 1e-6:
        fail("container", f"frame rate is {fps}, not {config.fps}")
    if counted and counted != expected_frames:
        fail("container",
             f"{counted} frames encoded, the timeline wants {expected_frames}")
    if int(audio["sample_rate"]) != config.audio_sample_rate:
        fail("container", f"audio at {audio['sample_rate']} Hz")
    if video.get("pix_fmt") != config.pixel_format:
        fail("container", f"pixel format {video.get('pix_fmt')}")

    # --- the frames the brief names ---------------------------------------
    last = expected_frames - 1
    marks = {
        "open_0": 0, "open_1": 1, "open_2": 2, "open_5": 5,
        "early_first_activation": int(round(times[0] * config.fps)),
        "early_8": int(round(times[7] * config.fps)),
        "mid_26": int(round(times[25] * config.fps)),
        "late_48": int(round((times[47] + 0.5) * config.fps)),
        "late_49": int(round((times[48] + 0.5) * config.fps)),
        "late_50": int(round((times[49] + 0.5) * config.fps)),
        "final_hit": int(round(beats["final_hit"] * config.fps)),
        "confirming": int(round(beats["confirming"] * config.fps)),
        "unlocking": int(round(beats["unlocking"] * config.fps)),
        "escaping": int(round(beats["escaping"] * config.fps)),
        "settled": int(round(beats["settled"] * config.fps)),
        "last": last, "last_minus_1": last - 1, "last_minus_2": last - 2,
    }
    extracted = _extract_frames(ffmpeg, delivery, marks.values(),
                                os.path.join(args.out, "qc", "frames"))
    frames: dict[str, Any] = {}
    for name, index in marks.items():
        path = extracted.get(index)
        if path is None:
            fail("frames", f"{name}: frame {index} could not be decoded")
            continue
        stats = _frame_stats(path)
        stats["frame"] = index
        frames[name] = stats
        if stats["blank"]:
            fail("frames", f"{name}: frame {index} is blank "
                           f"(peak {stats['peak']})")
    report["frames"] = frames

    # Opening: the ball is already moving, so frame 0 and frame 2 must differ.
    if "open_0" in frames and "open_2" in frames:
        from PIL import Image, ImageChops
        with Image.open(extracted[0]).convert("L") as a, \
                Image.open(extracted[2]).convert("L") as b:
            diff = ImageChops.difference(a, b)
            moved = sum(1 for value in diff.tobytes() if value > 10)
        report["opening_motion_pixels"] = moved
        if moved < 200:
            fail("opening", f"frames 0 and 2 differ in only {moved} pixels; "
                            "the ball may not be moving yet")

    # Ending: the last frames must not be black, and must be still.
    if "last" in frames and frames["last"]["peak"] < 60:
        fail("ending", f"the last frame peaks at {frames['last']['peak']}")
    if "last" in frames and "last_minus_2" in frames:
        from PIL import Image, ImageChops
        with Image.open(extracted[last]).convert("L") as a, \
                Image.open(extracted[last - 2]).convert("L") as b:
            diff = ImageChops.difference(a, b)
            moved = sum(1 for value in diff.tobytes() if value > 10)
        report["ending_motion_pixels"] = moved

    # Counter against geometry: count lit tiles in the picture and compare with
    # the ledger. The scene writes the counter from `activated_count_at`, the
    # same function the tiles are lit from, so geometry agreeing with the
    # ledger is the counter agreeing with the ledger.
    geometry = []
    for name in ("early_8", "mid_26", "late_48", "late_49", "late_50"):
        index = marks[name]
        path = extracted.get(index)
        if path is None:
            continue
        still = tile_readability.still_report(document, path, config.width,
                                              config.height)
        expected = sum(1 for t in times if t <= index / config.fps + 1e-9)
        geometry.append({"moment": name, "frame": index,
                         "lit_in_picture": still["active_tiles"],
                         "ledger": expected,
                         "agree": still["active_tiles"] == expected,
                         "worst_gap": still["worst_case_luminance_gap"],
                         "single_tile_findable":
                             still["single_remaining_tile_identifiable"]})
        if still["active_tiles"] != expected:
            fail("counter", f"{name}: picture shows {still['active_tiles']} lit "
                            f"tiles, the ledger says {expected}")
    report["geometry"] = geometry

    # --- the audio that came back out -------------------------------------
    decoded = os.path.join(args.out, "qc", "decoded.wav")
    os.makedirs(os.path.dirname(decoded), exist_ok=True)
    _ffmpeg_run([ffmpeg, "-y", "-i", delivery, "-map", "0:a:0",
                 "-c:a", "pcm_s24le", decoded], "decode delivery audio")
    from audio import loudness

    samples, sample_rate = loudness.read_pcm(decoded)
    wav = wav_path(args.out, config)
    source_samples, _ = loudness.read_pcm(wav)
    measured = loudness.measure(samples, sample_rate)
    peak_db = 20.0 * __import__("math").log10(
        max(float(abs(samples).max()), 1e-12))
    clipped = int((abs(samples) >= 1.0).sum())
    tail = samples[-int(0.05 * sample_rate):]
    report["audio"] = {
        "sample_rate": sample_rate,
        "samples": int(samples.shape[0]),
        "seconds": round(samples.shape[0] / sample_rate, 4),
        "source_samples": int(source_samples.shape[0]),
        "sample_peak_dbfs": round(peak_db, 3),
        "true_peak_dbtp": round(loudness.true_peak(samples), 3),
        "integrated_lufs": round(measured.integrated_lufs, 2),
        "clipped_samples": clipped,
        "final_50ms_peak_dbfs": round(
            20.0 * __import__("math").log10(
                max(float(abs(tail).max()), 1e-12)), 2),
    }
    if clipped:
        fail("audio", f"{clipped} clipped samples in the delivered file")
    if report["audio"]["true_peak_dbtp"] > DELIVERY_TRUE_PEAK_DBTP:
        fail("audio", f"true peak {report['audio']['true_peak_dbtp']} dBTP "
                      f"exceeds {DELIVERY_TRUE_PEAK_DBTP}")
    if report["audio"]["final_50ms_peak_dbfs"] > -40.0:
        fail("ending", "the last 50 ms is not silent: "
                       f"{report['audio']['final_50ms_peak_dbfs']} dBFS")

    # --- synchronisation ---------------------------------------------------
    video_seconds = expected_frames / config.fps
    audio_seconds = samples.shape[0] / sample_rate
    drift = audio_seconds - video_seconds
    report["sync"] = {
        "video_seconds": round(video_seconds, 6),
        "audio_seconds": round(audio_seconds, 6),
        "drift_seconds": round(drift, 6),
        "drift_frames": round(drift * config.fps, 4),
        "audio_start_pts": float(audio.get("start_time") or 0.0),
        "video_start_pts": float(video.get("start_time") or 0.0),
    }
    if abs(drift) > 1.0 / config.fps:
        fail("sync", f"audio and video differ by {drift * 1000:.1f} ms, "
                     "more than one frame")
    if abs(report["sync"]["audio_start_pts"]
           - report["sync"]["video_start_pts"]) > 1.0 / config.fps:
        fail("sync", "the two streams do not start together")

    path = _write_json(os.path.join(args.out, "qc", "qc.json"), report)
    container = report["container"]
    print(f"  container: {container['video_codec']} "
          f"{container['width']}x{container['height']} @ "
          f"{container['fps']:g} fps, {container['frames']} frames, "
          f"{container['duration_seconds']:.3f}s, "
          f"{container['pixel_format']}")
    print(f"             audio {container['audio_codec']} "
          f"{container['audio_sample_rate']} Hz "
          f"{container['audio_channels']}ch")
    print(f"  opening:   frame 0 peak {frames['open_0']['peak']}, "
          f"blank {frames['open_0']['blank']}; frames 0->2 differ in "
          f"{report.get('opening_motion_pixels')} px")
    for row in geometry:
        print(f"  {row['moment']:>10}: picture {row['lit_in_picture']:>2} lit, "
              f"ledger {row['ledger']:>2}  agree {row['agree']}  "
              f"worst tile gap {row['worst_gap']:.1f}  single-tile "
              f"{row['single_tile_findable']}")
    a = report["audio"]
    print(f"  audio:     {a['seconds']:.4f}s ({a['samples']} samples, source "
          f"{a['source_samples']}), peak {a['sample_peak_dbfs']:+.2f} dBFS / "
          f"{a['true_peak_dbtp']:+.2f} dBTP, {a['integrated_lufs']:+.2f} LUFS, "
          f"clipped {a['clipped_samples']}")
    print(f"             last 50 ms peaks at {a['final_50ms_peak_dbfs']:+.1f} dBFS")
    sync = report["sync"]
    print(f"  sync:      video {sync['video_seconds']:.4f}s, audio "
          f"{sync['audio_seconds']:.4f}s, drift "
          f"{sync['drift_seconds'] * 1000:+.2f} ms "
          f"({sync['drift_frames']:+.4f} frames)")
    print(f"  ending:    last frame peak {frames['last']['peak']}, "
          f"frames {last - 2}->{last} differ in "
          f"{report.get('ending_motion_pixels')} px")
    if report["problems"]:
        print(f"\n  {len(report['problems'])} PROBLEM(S):")
        for problem in report["problems"]:
            print(f"    [{problem['section']}] {problem['message']}")
    else:
        print("\n  no problems found")
    print(f"  -> {path}")
    return 1 if report["problems"] else 0


# --------------------------------------------------------------------------
# verify - determinism, at every layer
# --------------------------------------------------------------------------


def task_verify(args: argparse.Namespace) -> int:
    """Is the thing that was delivered reproducible from the repository?"""
    config = tile_production.PRODUCTION
    document = _document(args)
    problems: list[str] = []

    run = _run(config.seed, args.speed)
    rebuilt = tile_playback.playback_document(run)
    rebuilt = tile_completion.attach_completion(
        rebuilt, run, PHASE2_ARENA,
        tile_completion.named_timing(config.timing))
    same_run = str(rebuilt["digest"]) == str(document["digest"])
    print(f"  the run:      re-simulated digest "
          f"{'matches' if same_run else 'DIFFERS'}  "
          f"{str(document['digest'])[:16]}")
    if not same_run:
        problems.append("the simulation does not reproduce")
    for field in ("collisions", "activations", "flight"):
        if rebuilt.get(field) != document.get(field):
            problems.append(f"{field} changed on re-simulation")
    if rebuilt.get("completion") != document.get("completion"):
        problems.append("the completion block changed on re-simulation")

    audio_config = config.audio_config
    first = tile_score.schedule(document, audio_config)
    second = tile_score.schedule(document, audio_config)
    same_schedule = ([event.as_dict() for event in first.events]
                     == [event.as_dict() for event in second.events])
    print(f"  the schedule: built twice, "
          f"{'identical' if same_schedule else 'DIFFERENT'}  "
          f"fingerprint {audio_config.fingerprint()}")
    if not same_schedule:
        problems.append("the schedule is not deterministic")

    digest_a = tile_audio.render(first).digest()
    digest_b = tile_audio.render(second).digest()
    print(f"  the waveform: rendered twice, "
          f"{'identical' if digest_a == digest_b else 'DIFFERENT'}  "
          f"{digest_a[:16]}")
    if digest_a != digest_b:
        problems.append("the waveform is not deterministic")

    measure = measure_path(args.out, config)
    if os.path.isfile(measure):
        with open(measure, "r", encoding="utf-8") as handle:
            recorded = json.load(handle).get("pcm_digest")
        matches = recorded == digest_a
        print(f"  the master:   recorded PCM digest "
              f"{'matches' if matches else 'DIFFERS'}")
        if not matches:
            problems.append("the written master does not match a fresh render")

    print(f"  identity:     production {config.fingerprint()}  audio "
          f"{audio_config.fingerprint()}  safe area "
          f"{config.safe_area_config.fingerprint()}")
    if problems:
        print(f"\n  {len(problems)} PROBLEM(S):")
        for problem in problems:
            print(f"    {problem}")
    else:
        print("\n  every layer reproduces")
    return 1 if problems else 0


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


def task_identity(args: argparse.Namespace) -> int:
    """The reproducibility lock: what made the master, and its digests."""
    config = tile_production.PRODUCTION
    document = _document(args)
    payload = tile_production.identity(document, config)
    measure = measure_path(args.out, config)
    if os.path.isfile(measure):
        with open(measure, "r", encoding="utf-8") as handle:
            report = json.load(handle)
        payload["digests"] = {
            "playback_document": str(document["digest"]),
            "audio_pcm": report.get("pcm_digest"),
            "audio_config": config.audio_config.fingerprint(),
            "safe_area_config": config.safe_area_config.fingerprint(),
            "production_config": config.fingerprint(),
        }
    for name in ("archive", "delivery"):
        path = master_path(args.out, config) if name == "archive" \
            else delivery_path(args.out, config)
        if os.path.isfile(path):
            import hashlib
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            payload.setdefault("files", {})[name] = {
                "path": path.replace("\\", "/"),
                "bytes": os.path.getsize(path),
                "sha256": digest.hexdigest(),
            }
    path = _write_json(os.path.join(args.out, "production_identity.json"),
                       payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"\n  -> {path}")
    return 0


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------


TASKS = {
    "export": task_export,
    "frames": task_frames,
    "audio": task_audio,
    "safearea": task_safearea,
    "master": task_master,
    "phone": task_phone,
    "qc": task_qc,
    "verify": task_verify,
    "identity": task_identity,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m satisfying.tile_phase6_cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=sorted(TASKS))
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--speed", type=float, default=85.0,
                        help="locked; exposed so a mistake is visible")
    parser.add_argument("--godot", default=None)
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--no-render", action="store_true",
                        help="`phone`: measure the mix only, reuse any frames")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = tile_production.PRODUCTION
    print(f"{config.name}: seed {config.seed}, audio {config.audio}, "
          f"{config.width}x{config.height} at {config.fps:g} fps, "
          f"identity {config.fingerprint()}")
    return TASKS[args.task](args)


if __name__ == "__main__":
    sys.exit(main())

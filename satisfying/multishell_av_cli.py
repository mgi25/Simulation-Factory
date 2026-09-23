"""Build the reviewable multiplying-shell clips: one document, two consumers, one file.

    python -m satisfying.multishell_av_cli measure
    python -m satisfying.multishell_av_cli audio
    python -m satisfying.multishell_av_cli video --profile review
    python -m satisfying.multishell_av_cli mux --profile review
    python -m satisfying.multishell_av_cli stills
    python -m satisfying.multishell_av_cli sheets
    python -m satisfying.multishell_av_cli phone
    python -m satisfying.multishell_av_cli report

The order matters only in that `mux` needs the two halves to exist. Everything
is keyed by seed and every step re-derives the document from the seed, so a
stale intermediate cannot quietly survive a change: the digests are compared at
every join and a mismatch stops the build rather than producing a clip that
looks right and is not the run it claims to be.

Nothing here decides anything. It writes the files a person has to watch and
listen to, and the numbers that say which questions watching still has to
answer.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence

from satisfying import multishell_audio as audio
from satisfying import multishell_av as av
from satisfying import multishell_score as score
from satisfying import multishell_visual as visual
from satisfying.multishell_playback import (
    document_for,
    read_playback,
    verify_document,
    write_playback,
)

OUTPUT_ROOT = os.path.join("output", "category3_multishell_adjust_v3b")
VALIDATION_ROOT = os.path.join(
    "docs", "validation", "category3_multiplying_shell_adjust_v3b"
)


class CLIError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


def playback_path(seed: int) -> str:
    return os.path.join(OUTPUT_ROOT, "playback", f"seed_{seed}.playback.json")


def moments_path(seed: int) -> str:
    return os.path.join(OUTPUT_ROOT, "playback", f"seed_{seed}.moments.json")


def wav_path(seed: int) -> str:
    return os.path.join(OUTPUT_ROOT, "wav", f"seed_{seed}.wav")


def frames_dir(seed: int, profile: str) -> str:
    return os.path.join(OUTPUT_ROOT, "frames", f"seed_{seed}_{profile}")


def silent_path(seed: int, profile: str) -> str:
    return os.path.join(OUTPUT_ROOT, "silent", f"seed_{seed}_{profile}.mp4")


def clip_path(seed: int, profile: str) -> str:
    return os.path.join(OUTPUT_ROOT, "review", f"seed_{seed}_{profile}_av.mp4")


def stills_dir(seed: int) -> str:
    return os.path.join(OUTPUT_ROOT, "stills", f"seed_{seed}")


def sheet_path(seed: int) -> str:
    return os.path.join(VALIDATION_ROOT, "contact_sheets", f"seed_{seed}_sheet.png")


def profile_of(name: str, config: av.AVConfig = av.CONFIG) -> tuple[int, int, int, int]:
    """(width, height, fps, crf) for the named render profile."""
    if name == "review":
        return (config.review_width, config.review_height,
                config.review_fps, config.review_crf)
    if name == "full":
        return (config.full_width, config.full_height,
                config.full_fps, config.full_crf)
    raise CLIError(f"unknown profile {name!r}")


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("GODOT_BIN"), shutil.which("godot")):
        if candidate and os.path.exists(candidate):
            return candidate
        if candidate and shutil.which(candidate):
            return str(shutil.which(candidate))
    raise CLIError("Godot not found: pass --godot or set GODOT_BIN")


def find_ffmpeg(explicit: str | None) -> str:
    for candidate in (explicit, os.environ.get("FFMPEG_BIN"), shutil.which("ffmpeg")):
        if candidate and (os.path.exists(candidate) or shutil.which(candidate)):
            return str(shutil.which(candidate) or candidate)
    raise CLIError("ffmpeg not found: pass --ffmpeg or set FFMPEG_BIN")


def find_ffprobe(ffmpeg: str) -> str:
    """ffprobe beside the ffmpeg in use.

    Rewriting the whole path would also rename the directory, which on this
    machine is `ffmpeg-8.1.1-full_build` and does not exist as `ffprobe-...`.
    Only the executable's own name is substituted.
    """
    directory, name = os.path.split(ffmpeg)
    candidate = os.path.join(directory, name.replace("ffmpeg", "ffprobe", 1))
    if os.path.exists(candidate):
        return candidate
    found = shutil.which("ffprobe")
    if found:
        return found
    raise CLIError(f"ffprobe not found beside {ffmpeg}")


def godot_path(path: str) -> str:
    return os.path.abspath(path).replace("\\", "/")


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GODOT_PROJECT = os.path.join(REPO, "godot")
RENDER_SCENE = "res://scenes/MultishellRender.tscn"
SCENE_SCRIPT = "res://scripts/multishell_scene.gd"
RENDER_SCRIPT = "res://scripts/multishell_render.gd"


def check_scripts(godot: str) -> None:
    """Parse the GDScript before opening a window, exactly as Phase 2A does.

    A parse error does not make Godot exit - it opens its window and waits - so
    without this a broken script is a hung build rather than a message.
    """
    for script in (SCENE_SCRIPT, RENDER_SCRIPT):
        result = subprocess.run(
            [godot, "--path", GODOT_PROJECT, "--check-only", "--script", script],
            cwd=REPO, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        blob = (result.stdout or "") + (result.stderr or "")
        for line in blob.splitlines():
            if ("SCRIPT ERROR" in line or "Parse Error" in line
                    or "Failed to load" in line):
                raise CLIError(f"{script}: {line.strip()}")


def run_godot(godot: str, args: Sequence[str], label: str) -> str:
    # No `--headless`, and the scene rather than the script: the headless
    # display driver has no rendering device, so `get_texture().get_image()`
    # comes back empty. Phase 2A settled this and it is not re-litigated here.
    command = [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *args]
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join((result.stdout or "").splitlines()[-30:])
        errors = "\n".join((result.stderr or "").splitlines()[-30:])
        raise CLIError(f"{label}: Godot exited {result.returncode}\n"
                       f"--- stdout ---\n{tail}\n--- stderr ---\n{errors}")
    # GDScript reports parse and runtime errors on stderr without failing the
    # process, so a zero exit is not on its own proof the scene was built.
    for line in (result.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise CLIError(f"{label}: {line.strip()}")
    return result.stdout or ""


def run(command: Sequence[str], label: str) -> str:
    result = subprocess.run(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join((result.stderr or "").splitlines()[-25:])
        raise CLIError(f"{label}: exited {result.returncode}\n{tail}")
    return result.stdout or ""


def write_json(payload: Any, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=False)
        handle.write("\n")
    return path


# --------------------------------------------------------------------------
# The document, once
# --------------------------------------------------------------------------


def document(seed: int, reuse: bool = True) -> dict[str, Any]:
    """The canonical document for a seed, verified rather than trusted."""
    path = playback_path(seed)
    if reuse and os.path.exists(path):
        stored = read_playback(path)
        if verify_document(stored)["ok"]:
            # The moments are cheap and are derived from this module rather
            # than from the stored file, so they are rewritten every time. A
            # reused playback that kept a stale moments list is how a still set
            # silently stays one revision behind the one it documents.
            write_json(av.av_moments(stored), moments_path(seed))
            return stored
    fresh = document_for(seed)
    report = verify_document(fresh)
    if not report["ok"]:
        raise CLIError(f"seed {seed}: the document does not verify {report['checks']}")
    av.validate_shared_document(fresh)
    write_playback(fresh, path)
    write_json(av.av_moments(fresh), moments_path(seed))
    return fresh


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_measure(args: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        doc = document(seed, reuse=not args.fresh)
        row = av.candidate_row(doc, float(args.fps))
        rows.append(row)
        print(f"seed {seed:>6}  {row['duration_seconds']:5.2f}s  "
              f"split {row['first_split_seconds']:4.2f}s  "
              f"pop {row['population']:>2}  "
              f"pile {row['peak_cluster_balls']}x{row['longest_pile_seconds']:.2f}s  "
              f"ev/s {row['event_density_hz']:5.2f}  "
              f"poly {row['max_polyphony']:>2}  "
              f"sync {row['max_sync_error_frames']:.3f}fr  "
              f"{'ELIGIBLE' if row['eligible'] else 'REJECT: ' + rows[-1]['rejection_reasons'][0]}")
    payload = {
        "kind": "category3_multiplying_shell_av_candidates",
        "format": av.INTEGRATION_VERSION,
        "base_sha": av.BASE_SHA,
        "visual_sha": av.VISUAL_SHA,
        "audio_sha": av.AUDIO_SHA,
        "fps": float(args.fps),
        "integration_config": av.CONFIG.as_dict(),
        "integration_config_digest": av.CONFIG.fingerprint(),
        "visual_config_digest": visual.render_config_digest(),
        "audio_config_fingerprint": score.named_config(av.CONFIG.audio).fingerprint(),
        "seeds": list(args.seeds),
        "rows": rows,
    }
    print("->", write_json(payload, os.path.join(VALIDATION_ROOT, "av_candidates.json")))
    return 0


def cmd_detail(args: argparse.Namespace) -> int:
    """Every sub-report for one seed, written out in full."""
    for seed in args.seeds:
        doc = document(seed, reuse=not args.fresh)
        payload = {
            "identity": av.identity(doc),
            "sync_30": av.sync_audit(doc, 30.0),
            "sync_60": av.sync_audit(doc, 60.0),
            "camera": av.camera_report(doc, float(args.fps)),
            "spawn": av.spawn_report(doc),
            "population": av.population_report(doc, float(args.fps)),
            "retention": av.retention_report(doc),
            "density": av.density_report(doc),
            "lineage": av.lineage_audit(doc),
        }
        path = write_json(payload, os.path.join(
            VALIDATION_ROOT, "detail", f"seed_{seed}_detail.json"))
        print(f"seed {seed:>6} -> {path}")
    return 0


def cmd_audio(args: argparse.Namespace) -> int:
    for seed in args.seeds:
        doc = document(seed, reuse=not args.fresh)
        plan = score.schedule(doc, score.named_config(av.CONFIG.audio))
        if plan.playback_digest != doc["digest"]:
            raise CLIError(f"seed {seed}: the score is not this document")
        rendered = audio.render(plan)
        path = wav_path(seed)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        audio.write_master(rendered, path)
        report = audio.measure(rendered)
        loud, peak = report["loudness"], report["peak"]
        print(f"seed {seed:>6}  {plan.total_seconds:5.2f}s  "
              f"{loud['integrated_lufs']:>7} LUFS  "
              f"peak {loud['true_peak_dbtp']:>6} dBTP  "
              f"clipped {peak['clipped_samples']}  -> {path}")
    return 0


def cmd_video(args: argparse.Namespace) -> int:
    godot = find_godot(args.godot)
    check_scripts(godot)
    width, height, fps, _ = profile_of(args.profile)
    for seed in args.seeds:
        document(seed, reuse=not args.fresh)
        out_dir = frames_dir(seed, args.profile)
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        run_godot(godot, [
            f"--playback={godot_path(playback_path(seed))}",
            f"--out-dir={godot_path(out_dir)}",
            "--clip=1",
            f"--fps={fps}",
            f"--release={visual.RELEASE_SECONDS}",
            f"--hold={visual.END_HOLD_SECONDS}",
        ], f"clip seed {seed}")
        count = len([n for n in os.listdir(out_dir) if n.endswith(".png")])
        print(f"seed {seed:>6}  {count} frames at {fps:g} fps -> {out_dir}")
    return 0


def cmd_stills(args: argparse.Namespace) -> int:
    godot = find_godot(args.godot)
    check_scripts(godot)
    for seed in args.seeds:
        document(seed, reuse=not args.fresh)
        out_dir = stills_dir(seed)
        # Cleared rather than written over: the set is named by position in the
        # run, so a shorter set would leave the tail of a longer one behind and
        # the contact sheet would show two different still lists at once.
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        run_godot(godot, [
            f"--playback={godot_path(playback_path(seed))}",
            f"--out-dir={godot_path(out_dir)}",
            f"--moments={godot_path(moments_path(seed))}",
            "--stills=1",
            f"--release={visual.RELEASE_SECONDS}",
            f"--hold={visual.END_HOLD_SECONDS}",
        ], f"stills seed {seed}")
        made = sorted(n for n in os.listdir(out_dir) if n.endswith(".png"))
        print(f"seed {seed:>6}  {len(made)} stills -> {out_dir}")
    return 0


def cmd_mux(args: argparse.Namespace) -> int:
    """Join the frames and the master, and prove the join did not move anything."""
    ffmpeg = find_ffmpeg(args.ffmpeg)
    width, height, fps, crf = profile_of(args.profile)
    config = av.CONFIG
    rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        doc = document(seed, reuse=not args.fresh)
        out_dir = frames_dir(seed, args.profile)
        if not os.path.isdir(out_dir):
            raise CLIError(f"seed {seed}: render the frames first ({out_dir})")
        wav = wav_path(seed)
        if not os.path.exists(wav):
            raise CLIError(f"seed {seed}: render the audio first ({wav})")
        frame_count = len([n for n in os.listdir(out_dir) if n.endswith(".png")])
        target = clip_path(seed, args.profile)
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)

        # The score runs a tail past the final frame so the escape chord can
        # decay, so the video is always the shorter half and the last frame is
        # cloned to cover the difference. The pad is computed rather than
        # over-shot and trimmed: `-shortest` does not reliably cut a `tpad`
        # inside `filter_complex` - it left seed 949 five seconds long - and a
        # pad derived from the schedule is exact and reproducible besides.
        plan = score.schedule(doc, score.named_config(config.audio))
        video_seconds = frame_count / float(fps)
        pad_seconds = max(0.0, plan.total_seconds - video_seconds)
        pad = (f"tpad=stop_mode=clone:stop_duration={pad_seconds:.6f},"
               if pad_seconds > 1.0 / fps else "")
        command = [
            ffmpeg, "-y",
            "-framerate", f"{fps:g}",
            "-i", os.path.join(out_dir, "frame_%05d.png"),
            "-i", wav,
            "-filter_complex",
            f"[0:v]scale={width}:{height}:flags=lanczos,"
            f"{pad}format={config.pixel_format}[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", config.video_codec, "-crf", str(crf), "-preset", config.preset,
            "-c:a", config.audio_codec, "-b:a", config.audio_bitrate,
            "-ar", str(config.audio_sample_rate),
            "-movflags", "+faststart",
            target,
        ]
        run(command, f"mux seed {seed}")
        row = probe(ffmpeg, target, doc, frame_count, fps)
        rows.append(row)
        print(f"seed {seed:>6} -> {target}  "
              f"v {row['video_seconds']:.2f}s  a {row['audio_seconds']:.2f}s  "
              f"drift {row['av_drift_seconds'] * 1000:+.1f} ms  "
              f"{row['size_mb']:.1f} MB")
    write_json({
        "kind": "category3_multiplying_shell_av_muxed",
        "profile": args.profile,
        "integration_config_digest": config.fingerprint(),
        "rows": rows,
    }, os.path.join(VALIDATION_ROOT, f"mux_{args.profile}.json"))
    return 0


def probe(ffmpeg: str, path: str, doc: Mapping[str, Any],
          frame_count: int, fps: float) -> dict[str, Any]:
    """What actually landed in the container, from the container."""
    ffprobe = find_ffprobe(ffmpeg)
    out = run([ffprobe, "-v", "error", "-show_entries",
               "stream=codec_type,codec_name,width,height,nb_frames,duration,"
               "sample_rate,channels",
               "-show_entries", "format=duration,size",
               "-of", "json", path], f"probe {path}")
    info = json.loads(out)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    sound = next(s for s in info["streams"] if s["codec_type"] == "audio")
    video_seconds = float(video.get("duration") or 0.0)
    audio_seconds = float(sound.get("duration") or 0.0)
    return {
        "seed": int(doc["seed"]),
        "path": path,
        "playback_digest": str(doc["digest"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "aspect_is_9_16": abs(int(video["width"]) * 16 - int(video["height"]) * 9) <= 1,
        "video_codec": video["codec_name"],
        "audio_codec": sound["codec_name"],
        "sample_rate": int(sound["sample_rate"]),
        "channels": int(sound["channels"]),
        "source_frames": frame_count,
        "fps": fps,
        "video_seconds": video_seconds,
        "audio_seconds": audio_seconds,
        "av_drift_seconds": video_seconds - audio_seconds,
        "container_seconds": float(info["format"]["duration"]),
        "size_mb": float(info["format"]["size"]) / 1e6,
    }


def cmd_sheets(args: argparse.Namespace) -> int:
    """One contact sheet per seed from the event-centred stills."""
    ffmpeg = find_ffmpeg(args.ffmpeg)
    for seed in args.seeds:
        out_dir = stills_dir(seed)
        if not os.path.isdir(out_dir):
            raise CLIError(f"seed {seed}: render the stills first ({out_dir})")
        names = sorted(n for n in os.listdir(out_dir) if n.endswith(".png"))
        if not names:
            raise CLIError(f"seed {seed}: no stills in {out_dir}")
        listing = os.path.join(out_dir, "_sheet_inputs.txt")
        with open(listing, "w", encoding="utf-8") as handle:
            for name in names:
                handle.write(f"file '{os.path.abspath(os.path.join(out_dir, name))}'\n")
                handle.write("duration 1\n")
        target = sheet_path(seed)
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        columns = min(len(names), 4)
        rows = int(math.ceil(len(names) / columns))
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", listing,
             "-frames:v", "1",
             "-vf", f"scale=320:-1,tile={columns}x{rows}:margin=8:padding=6:color=0x101014",
             target], f"sheet seed {seed}")
        print(f"seed {seed:>6}  {len(names)} stills -> {target}")
    return 0


PHONE_WIDTH = 450
PHONE_HEIGHT = 800


def cmd_phone(args: argparse.Namespace) -> int:
    """The clip under the conditions a Shorts viewer actually meets it.

    Four checks, because they fail differently: a phone-sized picture loses
    fine damage marks, the Shorts chrome eats the bottom of the frame, a mono
    fold-down can cancel a panned pair, and a phone speaker has no low end at
    all. The first two are Phase 2A measurements re-run at the delivered size;
    the last two are Phase 2B measurements re-run on the delivered master.
    """
    ffmpeg = find_ffmpeg(args.ffmpeg)
    rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        doc = document(seed, reuse=not args.fresh)
        plan = score.schedule(doc, score.named_config(av.CONFIG.audio))
        rendered = audio.render(plan)
        measured = audio.measure(rendered)
        source = clip_path(seed, args.profile)
        if not os.path.exists(source):
            raise CLIError(f"seed {seed}: mux the clip first ({source})")

        phone = os.path.join(OUTPUT_ROOT, "phone", f"seed_{seed}_phone.mp4")
        os.makedirs(os.path.dirname(os.path.abspath(phone)), exist_ok=True)
        # 450x800, not Phase 2A's 405x720: that is the still size, and 405 is
        # odd, which libx264 will not encode in 4:2:0. 450x800 is exactly 9:16,
        # both even, and still inside the ~412 dp a Shorts player lays out to.
        run([ffmpeg, "-y", "-i", source,
             "-vf", f"scale={PHONE_WIDTH}:{PHONE_HEIGHT}:flags=lanczos",
             "-c:v", "libx264", "-crf", "23", "-preset", "medium",
             "-c:a", "copy", phone], f"phone seed {seed}")

        mono = os.path.join(OUTPUT_ROOT, "phone", f"seed_{seed}_mono.m4a")
        run([ffmpeg, "-y", "-i", source, "-vn", "-ac", "1",
             "-c:a", "aac", "-b:a", "128k", mono], f"mono seed {seed}")

        band = os.path.join(OUTPUT_ROOT, "phone", f"seed_{seed}_phoneband.m4a")
        run([ffmpeg, "-y", "-i", source, "-vn", "-ac", "1",
             "-af", "highpass=f=500,lowpass=f=6000",
             "-c:a", "aac", "-b:a", "128k", band], f"phone band seed {seed}")

        safe = visual.safe_area_report(doc)
        readable = visual.readability_report(doc, float(args.fps))
        rows.append({
            "seed": seed,
            "phone_clip": phone,
            "phone_size": [PHONE_WIDTH, PHONE_HEIGHT],
            "mono_audio": mono,
            "phone_band_audio": band,
            "mono_loss_db": measured["mono"]["mono_loss_db"],
            "mono_correlation": measured["mono"]["correlation"],
            "phone_relative_db": measured["phone"]["relative_to_master_db"],
            "phone_band_energy_percent": measured["phone"]["band_energy_percent"],
            "integrated_lufs": measured["loudness"]["integrated_lufs"],
            "true_peak_dbtp": measured["loudness"]["true_peak_dbtp"],
            "clipped_samples": measured["peak"]["clipped_samples"],
            "masking": measured["masking"],
            "safe_area": safe,
            "readability": readable,
        })
        print(f"seed {seed:>6}  mono {measured['mono']['mono_loss_db']:+.2f} dB  "
              f"corr {measured['mono']['correlation']:.3f}  "
              f"phone band {measured['phone']['relative_to_master_db']:+.2f} dB  "
              f"peak {measured['loudness']['true_peak_dbtp']:.2f} dBTP -> {phone}")
    write_json({
        "kind": "category3_multiplying_shell_av_phone",
        "profile": args.profile,
        "rows": rows,
    }, os.path.join(VALIDATION_ROOT, "phone_validation.json"))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    path = os.path.join(VALIDATION_ROOT, "av_candidates.json")
    if not os.path.exists(path):
        raise CLIError("run `measure` first")
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    axes = [
        ("first split s", "first_split_seconds", "{:.2f}"),
        ("split reads s", "first_split_reads_in_seconds", "{:.2f}"),
        ("splits read %", "splits_reading_as_two_fraction", "{:.0%}"),
        ("population", "population", "{:d}"),
        ("families", "families", "{:d}"),
        ("breaks", "breaks", "{:d}"),
        ("near misses", "near_misses", "{:d}"),
        ("peak cluster", "peak_cluster_balls", "{:d}"),
        ("pile s", "longest_pile_seconds", "{:.2f}"),
        ("ev/s", "event_density_hz", "{:.2f}"),
        ("peak ev/s", "peak_events_per_second", "{:d}"),
        ("max poly", "max_polyphony", "{:d}"),
        ("late overlap", "late_overlap_fraction", "{:.0%}"),
        ("poly growth", "polyphony_growth_ratio", "{:.1f}x"),
        ("cam peak", "camera_peak_velocity", "{:.3f}"),
        ("static tail s", "static_tail_seconds", "{:.2f}"),
        ("longest gap s", "longest_event_gap_seconds", "{:.2f}"),
        ("duration s", "duration_seconds", "{:.2f}"),
        ("sync fr", "max_sync_error_frames", "{:.3f}"),
    ]
    seeds = [row["seed"] for row in payload["rows"]]
    print(f"{'axis':<16}" + "".join(f"{seed:>10}" for seed in seeds))
    print("-" * (16 + 10 * len(seeds)))
    for label, key, fmt in axes:
        cells = []
        for row in payload["rows"]:
            value = row.get(key)
            cells.append("-" if value is None else fmt.format(value))
        print(f"{label:<16}" + "".join(f"{cell:>10}" for cell in cells))
    print("-" * (16 + 10 * len(seeds)))
    print(f"{'eligible':<16}" + "".join(
        f"{('yes' if row['eligible'] else 'NO'):>10}" for row in payload["rows"]))
    for row in payload["rows"]:
        for reason in row["rejection_reasons"]:
            print(f"  seed {row['seed']}: {reason}")
    return 0


# --------------------------------------------------------------------------


def seed_list(raw: str) -> list[int]:
    return [int(part) for part in raw.replace(" ", ",").split(",") if part]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="multishell_av_cli", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--seeds", type=seed_list, default=list(av.CANDIDATE_SEEDS),
        help="comma-separated seeds; a greedy nargs list would swallow the "
             "subcommand, so this takes 949,12004 rather than 949 12004")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--profile", default="review", choices=("review", "full"))
    parser.add_argument("--godot", default=None)
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--fresh", action="store_true",
                        help="re-derive every document instead of reusing")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, function, help_text in (
        ("measure", cmd_measure, "one comparison row per candidate"),
        ("detail", cmd_detail, "every sub-report for each seed"),
        ("audio", cmd_audio, "render the 48 kHz masters"),
        ("video", cmd_video, "render the frames"),
        ("mux", cmd_mux, "join frames and master into a review MP4"),
        ("stills", cmd_stills, "the event-centred stills"),
        ("sheets", cmd_sheets, "contact sheets from the stills"),
        ("phone", cmd_phone, "phone, mono and phone-band validation"),
        ("report", cmd_report, "print the comparison table"),
    ):
        sub.add_parser(name, help=help_text).set_defaults(func=function)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except CLIError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

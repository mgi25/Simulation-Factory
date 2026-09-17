"""The Race #2 audio pass: the locked picture, three soundtracks, one winner.

    python tools/race2_v322_audio.py all

Stages, each runnable on its own:

    diagnose   what the V32 mix is made of, and where the continuous texture is
    build      three PCM masters - CONTROL, Mix A, Mix B - from the same replay
    mux        each master onto the locked video, by stream copy
    lock       Part P: prove all three carry the same video, byte for byte
    compare    the listening pairs, and a phone/mono proof
    report     loudness, fatigue, the event timeline, the mono fold-down
    qc         every acceptance number in the brief, checked
    all        all of the above, in order

## The visual lock is structural, not a promise

**Nothing in this file renders, simulates, re-times or re-encodes a picture.**
`mux` takes `exports/race2_v321_track_geometry/race2_switchyard_final_candidate.mp4`
- the shipping V32.1 film - and runs `ffmpeg -c:v copy`, which copies the H.264
elementary stream across without a decoder or an encoder ever touching it. The
three outputs therefore cannot differ visually from the source or from each
other, and `lock` demonstrates it two ways: the MD5 of the copied video stream,
and `framemd5` over all 1150 *decoded* frames.

That is a stronger guarantee than re-rendering and comparing would be, because
re-rendering has to be checked and this cannot be wrong.

## The CONTROL is the shipped mix, not a reconstruction of it

`stage_build` builds CONTROL through `audio.marble.build_race_audio`, untouched
by this branch, and asserts its SHA-256 against the WAV V32.1 delivered. If that
assertion ever fails, the comparison is meaningless and the stage stops.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import numpy as np

COURSE = "switchyard"
SEED = 8
CAMERA = "output/race2/v31_readability/RB"
FPS = 60
FRAMES = 1150

OUT = "output/race2/v322_audio"
WORK = os.path.join(OUT, "work")
DOCS = "docs/validation/race2/v322_audio"
EXPORT = "exports/race2_v322_audio"

#: The finished V32.1 film. Everything this pass delivers is this file's video
#: stream with a different audio stream beside it.
LOCKED = os.path.join(WORK, "locked_visual.mp4")
LOCKED_SOURCES = (
    LOCKED,
    "exports/race2_v321_track_geometry/race2_switchyard_final_candidate.mp4",
    "exports/race2_v321_track_geometry/A/race2_switchyard_final.mp4",
)

#: The audio V32.1 shipped, as `audio.marble` produces it. Asserted, not assumed.
CONTROL_SHA256 = "8ceb9b24100440d9"

VARIANTS = ("CONTROL", "A", "B")
AUDIO_BITRATE = "256k"
PHONE_SIZE = (270, 480)

#: Delivery, from the brief: near -14 LUFS, true peak at or under -1.0 dBTP.
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.0
TRUE_PEAK_CEILING_DBTP = -1.0


class AudioError(RuntimeError):
    pass


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise AudioError(f"{name} is not on PATH")
    return found


def _run(command: Sequence[str], label: str) -> str:
    done = subprocess.run(list(command), cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise AudioError(f"{label} failed:\n{(done.stderr or done.stdout)[-2500:]}")
    return done.stdout or ""


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: str, payload: Any) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=False)
        handle.write("\n")
    return path


def locked_film() -> str:
    for candidate in LOCKED_SOURCES:
        if os.path.isfile(candidate):
            return candidate
    raise AudioError(
        "the locked V32.1 film is not here. Expected one of:\n  "
        + "\n  ".join(LOCKED_SOURCES))


def load():
    from race2.presentation import load_film

    replay = os.path.join("output/race2", f"race2_{COURSE}_{SEED}.replay.json")
    track = os.path.join(CAMERA, f"race2_{COURSE}_{SEED}.cameras.json")
    for path in (replay, track):
        if not os.path.isfile(path):
            raise AudioError(f"missing {path}")
    return load_film(replay, track, master_frames=FRAMES)


def wav_path(variant: str) -> str:
    return os.path.join(WORK, f"race2_{COURSE}_{SEED}_{variant}.wav")


def film_path(variant: str) -> str:
    return os.path.join(EXPORT, f"race2_{COURSE}_{variant.lower()}.mp4")


# --- diagnose ----------------------------------------------------------------


def stage_diagnose(args) -> dict[str, Any]:
    """Where the continuous texture in the V32 mix comes from, layer by layer.

    Every stem `audio.marble` places is rebuilt in isolation at its designed
    level and measured three ways: its band profile, how much of the film it is
    active over, and how far it travels. The two numbers that matter are in
    `control_summary`: the rolling pair's share of everything above 2 kHz, and
    how flat the two beds' own control signals are.
    """
    from audio import loudness as meter, marble
    from audio.synthesis import (
        Noise, SAMPLE_RATE, add_into, db_to_gain, high_pass, low_pass,
        seconds_to_samples, silence, stable_seed,
    )
    from sloped import presentation as pres

    replay, track, clock = load()
    length = seconds_to_samples(clock.duration, SAMPLE_RATE)
    seed_base = int(replay.get("seed", 0))

    stems: dict[str, np.ndarray] = {}

    ambience = marble.ambience_bed(length, stable_seed("ambience", seed_base))
    marble._to_rms(ambience, marble.LEVEL_AMBIENCE)
    stems["ambience"] = np.asarray(ambience, dtype=np.float64)

    speeds = pres.rolling(replay, clock)
    bed = marble.rolling_bed(speeds, length, stable_seed("rolling", seed_base))
    marble._to_rms(bed, marble.LEVEL_ROLL)
    stems["rolling_bed"] = np.asarray(bed, dtype=np.float64)

    rattle = sorted(dict(pres.contact_energy(replay, clock)).items())
    grain = Noise(stable_seed("rattle", seed_base)).fill(length)
    high_pass(grain, 1700.0, sample_rate=SAMPLE_RATE, stages=2)
    low_pass(grain, 8200.0, sample_rate=SAMPLE_RATE, stages=1)
    if rattle:
        cursor = 0
        times = [row[0] for row in rattle]
        for index in range(length):
            when = index / SAMPLE_RATE
            while cursor + 1 < len(times) and times[cursor + 1] <= when:
                cursor += 1
            low = rattle[cursor]
            high = rattle[min(cursor + 1, len(rattle) - 1)]
            span = max(1e-6, high[0] - low[0])
            blend = min(1.0, max(0.0, (when - low[0]) / span))
            grain[index] *= (low[1] + (high[1] - low[1]) * blend) ** 1.2
    marble._to_rms(grain, marble.LEVEL_ROLL - 6.0)
    stems["rolling_grain"] = np.asarray(grain, dtype=np.float64)

    music = marble.music_bed(length, stable_seed("music", seed_base),
                             build_from=max(0.0, clock.duration - 4.0))
    marble._to_rms(music, marble.LEVEL_MUSIC)
    stems["music"] = np.asarray(music, dtype=np.float64)

    hits = pres.impacts(replay, clock)
    impacts = silence(length)
    for event in hits:
        force = min(1.0, max(0.0, (event.magnitude - marble.IMPACT_SOFT)
                             / (marble.IMPACT_HARD - marble.IMPACT_SOFT)))
        level = (marble.LEVEL_IMPACT_QUIET
                 + (marble.LEVEL_IMPACT_LOUD - marble.LEVEL_IMPACT_QUIET) * force)
        add_into(impacts, marble.impact_cue(
            event.magnitude, marble.BODY_HZ.get(event.module, marble.BODY_DEFAULT),
            stable_seed("impact", seed_base, event.marble, round(event.replay, 4))),
            int(round(event.at * SAMPLE_RATE)), db_to_gain(level))
    stems["impacts"] = np.asarray(impacts, dtype=np.float64)

    crossings = sorted((float(e["t"]), int(e["id"]), int(e["order"]))
                       for e in replay["events"] if e["kind"] == "finish_line")
    photo = marble._photo_finishes(crossings)
    line = silence(length)
    for when, who, order in crossings:
        output = clock.at(when)
        if output is None:
            continue
        winner = order == 1
        level = marble.LEVEL_CROSS_WINNER if winner else (
            marble.LEVEL_CROSS_PHOTO if order in photo else marble.LEVEL_CROSS_OTHER)
        add_into(line, marble.crossing_cue(
            stable_seed("cross", seed_base, who), winner=winner),
            int(round(output * SAMPLE_RATE)), db_to_gain(level))
    stems["crossings"] = np.asarray(line, dtype=np.float64)

    rows = []
    for name, signal in stems.items():
        stereo = np.stack((signal, signal), axis=1)
        window = SAMPLE_RATE // 10
        count = signal.size // window
        block = signal[:count * window].reshape(count, window)
        level = 20.0 * np.log10(np.maximum(np.sqrt(np.mean(block * block, axis=1)), 1e-12))
        median = float(np.median(level[level > -110.0]))
        overall = 20.0 * math.log10(max(float(np.sqrt(np.mean(signal ** 2))), 1e-12))
        rows.append({
            "stem": name,
            "rms_dbfs": round(overall, 2),
            "peak_dbfs": round(
                20.0 * math.log10(max(float(np.max(np.abs(signal))), 1e-12)), 2),
            "active_fraction": round(float(np.mean(level > overall - 25.0)), 4),
            "within_10db_of_median": round(
                float(np.mean(np.abs(level - median) <= 10.0)), 4),
            "bands": meter.band_profile(stereo),
        })

    # The two control signals, and how little they move.
    fastest = max(max(r[1], r[2]) for r in speeds) or 1.0
    drive = np.array([min(1.0, (0.55 * r[1] + 0.45 * r[2]) / fastest)
                      ** marble.ROLL_RESPONSE for r in speeds])
    grain_control = np.array([row[1] ** 1.2 for row in rattle])
    span = min(drive.size, grain_control.size)

    def per_second(series: np.ndarray, times: Sequence[float]) -> list[float]:
        out = []
        for index in range(int(clock.duration)):
            mask = [i for i, t in enumerate(times) if index <= t < index + 1]
            out.append(round(float(np.mean(series[mask])), 4) if mask else None)
        return out

    control = {
        "rolling_drive": {
            "per_second": per_second(drive, [r[0] for r in speeds]),
            "p5": round(float(np.percentile(drive, 5)), 4),
            "p95": round(float(np.percentile(drive, 95)), 4),
        },
        "rattle_grain": {
            "per_second": per_second(grain_control, [r[0] for r in rattle]),
            "p5": round(float(np.percentile(grain_control, 5)), 4),
            "p95": round(float(np.percentile(grain_control, 95)), 4),
        },
        "correlation": round(float(np.corrcoef(
            drive[:span], grain_control[:span])[0, 1]), 4),
    }
    for key in ("rolling_drive", "rattle_grain"):
        rows_ = [v for v in control[key]["per_second"] if v is not None]
        control[key]["per_second_span_db"] = round(
            20.0 * math.log10(max(rows_) / max(min(rows_), 1e-9)), 2)

    # The finished CONTROL mix, if it has been built.
    summary: dict[str, Any] = {}
    path = wav_path("CONTROL")
    if os.path.isfile(path):
        samples, rate = meter.read_pcm(path)
        summary = {
            "loudness": meter.measure(samples, rate).as_dict(),
            "energy_above_2khz_pct": meter.energy_above(samples, 2000.0, rate),
            "fatigue": meter.fatigue_report(samples, rate),
        }

    report = {
        "film": {"course": COURSE, "seed": SEED, "frames": FRAMES,
                 "fps": clock.fps, "duration": round(clock.duration, 6)},
        "stems": rows,
        "control_signals": control,
        "control_mix": summary,
        "finding": (
            "Everything above 2 kHz in the V32 mix is the rolling pair and it "
            "never stops. The rattle grain is band-limited 1.7-8.2 kHz, is "
            "active in 100% of 100 ms windows and sits within 10 dB of its own "
            "median in 99% of them; its control signal's per-second mean spans "
            f"{control['rattle_grain']['per_second_span_db']} dB across the "
            "whole race, and it is anti-correlated with the rolling bed's drive "
            f"(r = {control['correlation']}), so the two layers fill each "
            "other's gaps and the sum is flatter than either."),
    }
    _write_json(os.path.join(DOCS, "diagnosis.json"), report)

    print("diagnose: the V32 mix, stem by stem")
    print(f"  {'stem':14s} {'rms':>8s} {'peak':>8s} {'active':>7s} {'flat':>6s}  "
          f"{'>2kHz':>6s}")
    for row in rows:
        above = sum(v for k, v in row["bands"].items()
                    if int(k.split("-")[0]) >= 2000)
        print(f"  {row['stem']:14s} {row['rms_dbfs']:8.2f} {row['peak_dbfs']:8.2f} "
              f"{row['active_fraction'] * 100:6.1f}% {row['within_10db_of_median'] * 100:5.1f}% "
              f"{above:5.1f}%")
    print(f"  rolling drive per-second span {control['rolling_drive']['per_second_span_db']} dB")
    print(f"  rattle grain per-second span  {control['rattle_grain']['per_second_span_db']} dB")
    print(f"  correlation between them      {control['correlation']}")
    print(f"  wrote {os.path.join(DOCS, 'diagnosis.json')}")
    return report


# --- build -------------------------------------------------------------------


def stage_build(args) -> dict[str, str]:
    """Three PCM masters from one replay: the shipped mix, and the two new ones."""
    from audio import asmr, marble
    from audio.wav_io import write_wav

    replay, track, clock = load()
    os.makedirs(WORK, exist_ok=True)
    out: dict[str, str] = {}
    reports: dict[str, Any] = {}

    control = marble.build_race_audio(replay, track, clock)
    path = wav_path("CONTROL")
    write_wav(path, control.left, control.right, sample_rate=control.sample_rate)
    digest = _sha256(path)
    if not digest.startswith(CONTROL_SHA256):
        raise AudioError(
            f"the CONTROL mix is not the one V32.1 shipped\n"
            f"  expected sha256 starting {CONTROL_SHA256}\n  got             {digest[:16]}\n"
            f"  `audio.marble` must not change on this branch")
    out["CONTROL"] = path
    reports["CONTROL"] = {
        "source": "audio.marble.build_race_audio, unchanged",
        "sha256": digest,
        "placed": control.placed,
        "seconds": round(control.seconds, 6),
    }
    print(f"build: CONTROL {control.seconds:.4f} s  sha256 {digest[:16]}  "
          f"placed {control.placed}")

    for name in ("A", "B"):
        mix = asmr.build_asmr_audio(replay, track, clock, name)
        path = wav_path(name)
        write_wav(path, mix.left, mix.right, sample_rate=mix.sample_rate)
        out[name] = path
        reports[name] = dict(mix.report, sha256=_sha256(path),
                             placed=mix.placed, seconds=round(mix.seconds, 6))
        loud = mix.report["loudness"]
        print(f"build: Mix {name} ({mix.report['profile_title']}) {mix.seconds:.4f} s  "
              f"{loud['integrated_lufs']} LUFS  {loud['true_peak_dbtp']} dBTP  "
              f"LRA {loud['lra_lu']}")
        print(f"  placed {mix.placed}")

    for name, path in out.items():
        expected = FRAMES * (48000 // FPS) * 2 * 3 + 44
        actual = os.path.getsize(path)
        if actual != expected:
            raise AudioError(
                f"{name}: {actual} bytes, expected {expected} "
                f"({FRAMES} frames x {48000 // FPS} samples x 2 channels x 24 bit)")

    _write_json(os.path.join(DOCS, "masters.json"), reports)
    return out


# --- mux ---------------------------------------------------------------------


def stage_mux(args) -> dict[str, str]:
    """Each master onto the locked picture, by stream copy.

    `-c:v copy` is the whole visual lock. ffmpeg demuxes the H.264 stream out of
    the V32.1 candidate and muxes it straight into the new container: no decode,
    no encode, no filter graph, no scaling and no colour conversion is applied to
    it, so the bytes that arrive are the bytes that left.
    """
    source = locked_film()
    ffmpeg = _tool("ffmpeg")
    os.makedirs(EXPORT, exist_ok=True)
    out: dict[str, str] = {}
    for variant in VARIANTS:
        audio = wav_path(variant)
        if not os.path.isfile(audio):
            raise AudioError(f"missing {audio}; run `build` first")
        target = film_path(variant)
        _run([ffmpeg, "-y", "-i", source, "-i", audio,
              "-map", "0:v:0", "-map", "1:a:0",
              "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000",
              "-movflags", "+faststart", "-shortest", target],
             f"mux {variant}")
        out[variant] = target
        print(f"mux: {variant:8s} -> {target}  "
              f"{os.path.getsize(target) / (1024 * 1024):.1f} MiB")
    return out


# --- lock --------------------------------------------------------------------


def _video_stream_md5(path: str) -> str:
    ffmpeg = _tool("ffmpeg")
    text = _run([ffmpeg, "-v", "error", "-i", path, "-map", "0:v:0", "-c", "copy",
                 "-f", "md5", "-"], f"hash the video stream of {path}")
    return text.strip().split("=")[-1]


def _decoded_frames_md5(path: str) -> tuple[str, int]:
    """MD5 over every decoded frame, and how many there were.

    `-f framemd5` prints one hash per decoded frame. Hashing that output gives a
    single number that changes if any pixel of any frame changes - which is what
    the brief asks to see, over and above the elementary-stream comparison.
    """
    ffmpeg = _tool("ffmpeg")
    text = _run([ffmpeg, "-v", "error", "-i", path, "-map", "0:v:0",
                 "-f", "framemd5", "-"], f"framemd5 {path}")
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), len(lines)


def stage_lock(args) -> dict[str, Any]:
    """Part P: the three films carry one picture, proved twice."""
    source = locked_film()
    targets = {"SOURCE (V32.1)": source}
    for variant in VARIANTS:
        path = film_path(variant)
        if not os.path.isfile(path):
            raise AudioError(f"missing {path}; run `mux` first")
        targets[variant] = path

    rows: dict[str, Any] = {}
    for label, path in targets.items():
        stream = _video_stream_md5(path)
        frames, count = _decoded_frames_md5(path)
        rows[label] = {"path": path, "video_stream_md5": stream,
                       "decoded_frames_sha256": frames, "frames": count}

    reference = rows["SOURCE (V32.1)"]
    identical = all(
        row["video_stream_md5"] == reference["video_stream_md5"]
        and row["decoded_frames_sha256"] == reference["decoded_frames_sha256"]
        and row["frames"] == reference["frames"]
        for row in rows.values())

    # The audio, by contrast, must differ in all three.
    audio_hashes = {v: _sha256(wav_path(v)) for v in VARIANTS}
    distinct = len(set(audio_hashes.values())) == len(VARIANTS)

    report = {
        "video": rows,
        "video_identical": identical,
        "frames": reference["frames"],
        "audio_sha256": audio_hashes,
        "audio_all_distinct": distinct,
        "method": (
            "mux is `ffmpeg -c:v copy`, so no decoder or encoder touches the "
            "picture. Both the copied elementary stream's MD5 and a SHA-256 over "
            "framemd5 of all decoded frames are compared against the V32.1 film."),
    }
    _write_json(os.path.join(DOCS, "visual_lock.json"), report)

    print("lock: the picture, across all three films")
    for label, row in rows.items():
        print(f"  {label:16s} stream {row['video_stream_md5']}  "
              f"frames {row['frames']}  decoded {row['decoded_frames_sha256'][:16]}")
    print(f"  video identical to V32.1: {identical}")
    print(f"  audio all distinct:       {distinct}")
    if not identical:
        raise AudioError("the video streams are NOT identical - the visual lock is broken")
    if not distinct:
        raise AudioError("two variants carry the same audio")
    return report


# --- compare -----------------------------------------------------------------

#: The listening pairs the brief asks for, plus the section each one is judged on.
PAIRS = (("CONTROL", "A"), ("CONTROL", "B"), ("A", "B"))
SEGMENTS = (("full", 0.0, None), ("sprint", 12.0, None), ("start", 0.0, 6.0))


def stage_compare(args) -> dict[str, str]:
    """Sequential A/B films: the same picture twice, one soundtrack each.

    Sequential rather than simultaneous, because there is no honest way to play
    two mixes at once and the brief says so. Each file is `<first>` then
    `<second>`, back to back, with a title frame on neither - a cut between two
    identical pictures is invisible, so what a reviewer hears change is the only
    thing that changed.
    """
    ffmpeg = _tool("ffmpeg")
    os.makedirs(EXPORT, exist_ok=True)
    out: dict[str, str] = {}
    for first, second in PAIRS:
        for label, start, end in SEGMENTS:
            pieces = []
            for variant in (first, second):
                source = film_path(variant)
                if not os.path.isfile(source):
                    raise AudioError(f"missing {source}; run `mux` first")
                piece = os.path.join(WORK, f"seg_{label}_{variant}.mp4")
                command = [ffmpeg, "-y", "-ss", f"{start:.3f}"]
                if end is not None:
                    command += ["-to", f"{end:.3f}"]
                command += ["-i", source, "-c:v", "copy", "-c:a", "aac",
                            "-b:a", AUDIO_BITRATE, piece]
                _run(command, f"cut {label} {variant}")
                pieces.append(piece)
            listing = os.path.join(WORK, f"concat_{label}_{first}_{second}.txt")
            with open(listing, "w", encoding="utf-8") as handle:
                for piece in pieces:
                    handle.write(f"file '{os.path.abspath(piece)}'\n")
            target = os.path.join(EXPORT, f"compare_{label}_{first}_{second}.mp4")
            _run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", listing,
                  "-c", "copy", "-movflags", "+faststart", target],
                 f"join {label} {first}|{second}")
            out[f"{label}_{first}_{second}"] = target
            print(f"compare: {label:6s} {first}|{second} -> {target}")

    # A phone review of each variant, and a mono/small-speaker WAV beside it.
    from audio import loudness as meter
    from audio.wav_io import write_wav
    from array import array

    for variant in VARIANTS:
        phone = os.path.join(EXPORT, f"race2_{COURSE}_{variant.lower()}_phone_270x480.mp4")
        _run([ffmpeg, "-y", "-i", film_path(variant), "-vf",
              f"scale={PHONE_SIZE[0]}:{PHONE_SIZE[1]}:flags=lanczos",
              "-c:v", "libx264", "-preset", "slow", "-crf", "18",
              "-pix_fmt", "yuv420p", "-movflags", "+faststart",
              "-c:a", "aac", "-b:a", "128k", phone], f"phone review {variant}")
        out[f"phone_{variant}"] = phone

        samples, rate = meter.read_pcm(wav_path(variant))
        folded = meter.phone_filter(samples, rate)
        column = array("d", folded[:, 0])
        small = os.path.join(EXPORT, f"race2_{COURSE}_{variant.lower()}_smallspeaker.wav")
        write_wav(small, column, column, sample_rate=rate)
        out[f"smallspeaker_{variant}"] = small
        print(f"compare: phone {variant:8s} -> {phone}")
    return out


# --- report ------------------------------------------------------------------


def stage_report(args) -> dict[str, Any]:
    """Loudness, fatigue, mono and the event timeline, for all three mixes."""
    from audio import asmr, loudness as meter

    replay, track, clock = load()
    rows: dict[str, Any] = {}
    for variant in VARIANTS:
        path = wav_path(variant)
        if not os.path.isfile(path):
            raise AudioError(f"missing {path}; run `build` first")
        samples, rate = meter.read_pcm(path)
        loud = meter.measure(samples, rate)
        rows[variant] = {
            "loudness": loud.as_dict(),
            "energy_above_2khz_pct": meter.energy_above(samples, 2000.0, rate),
            "energy_above_5khz_pct": meter.energy_above(samples, 5000.0, rate),
            "fatigue": meter.fatigue_report(samples, rate),
            "mono": meter.mono_compatibility(samples, rate),
            "short_term_span_db": round(float(
                np.max(meter.band_series(samples, 20.0, 20000.0, rate, 0.5))
                - np.min(meter.band_series(samples, 20.0, 20000.0, rate, 0.5))), 2),
            "duty_cycle": {
                "2000-5000": round(meter.duty_cycle(samples, 2000.0, 5000.0, rate), 4),
                "5000-10000": round(meter.duty_cycle(samples, 5000.0, 10000.0, rate), 4),
            },
        }

    # The event timeline: every cue the two new mixes place, with its second.
    telemetry = asmr.telemetry(replay, track, clock)
    timeline = {
        "ticks": [[round(c.at, 4), round(c.strength, 3), c.detail["marble"]]
                  for c in asmr.rail_ticks(replay, clock, telemetry)],
        "clicks": [[round(c.at, 4), round(c.strength, 3),
                    c.detail["a"], c.detail["b"], c.detail["speed"]]
                   for c in asmr.marble_clicks(replay, clock, telemetry)],
        "contacts": [[round(c.at, 4), round(c.strength, 3), c.detail["module"]]
                     for c in asmr.track_contacts(replay, track, clock)],
        "mechanisms": [[round(c.at, 4), c.detail["module"], c.detail["marble"]]
                       for c in asmr.mechanism_hits(replay, track, clock, telemetry)],
        "points": [[round(c.at, 4), c.detail["pan"]]
                   for c in asmr.points_switches(replay, clock, telemetry)],
        "finishes": [[round(c.at, 4), c.detail["order"], c.detail["marble"]]
                     for c in asmr.crossings(replay, clock)],
    }
    timeline["counts"] = {key: len(value) for key, value in timeline.items()}

    masters = os.path.join(DOCS, "masters.json")
    detail = json.load(open(masters, encoding="utf-8")) if os.path.isfile(masters) else {}

    report = {"mixes": rows, "timeline": timeline, "masters": detail,
              "telemetry": telemetry.as_dict()}
    _write_json(os.path.join(DOCS, "audio_report.json"), report)

    print(f"report: {'mix':9s} {'LUFS':>7s} {'LRA':>6s} {'dBTP':>7s} "
          f"{'>2kHz':>7s} {'5-10k flat':>11s} {'5-10k span':>11s} {'quiet':>7s}")
    for variant, row in rows.items():
        fatigue = row["fatigue"]["fatigue_bands"]["5000-10000"]
        loud = row["loudness"]
        print(f"        {variant:9s} {loud['integrated_lufs']:7.2f} {loud['lra_lu']:6.2f} "
              f"{loud['true_peak_dbtp']:7.2f} {row['energy_above_2khz_pct']:6.1f}% "
              f"{fatigue['within_db'] * 100:10.1f}% {fatigue['span_db']:10.1f} "
              f"{fatigue['quiet_fraction'] * 100:6.1f}%")
    print(f"  timeline {timeline['counts']}")
    print(f"  wrote {os.path.join(DOCS, 'audio_report.json')}")
    return report


# --- pictures of the sound ---------------------------------------------------


def _spectrogram(samples: np.ndarray, rate: int, width: int = 1150,
                 height: int = 320, floor_db: float = -96.0) -> "Image.Image":
    """A log-frequency spectrogram, drawn so texture and transients look different.

    The whole diagnosis of this pass is "continuous bed" versus "discrete
    events", and that distinction is *visible*: a bed is a horizontal band that
    never breaks, and events are vertical strikes with gaps between them. One
    column per output frame, so the picture is on the film's own grid and a
    feature can be read off against a timecode.
    """
    from PIL import Image

    mono = samples.mean(axis=1)
    size = 2048
    hop = max(1, mono.size // width)
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1.0 / rate)
    # Log-spaced rows from 40 Hz to 16 kHz, which is where everything in this mix
    # lives and is how the ear spaces frequency anyway.
    edges = np.geomspace(40.0, 16000.0, height + 1)
    bins = [np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0]
            for i in range(height)]
    for index, chosen in enumerate(bins):
        if chosen.size == 0:
            bins[index] = np.array([int(np.argmin(np.abs(freqs - edges[index])))])

    picture = np.zeros((height, width), dtype=np.float64)
    for column in range(width):
        start = column * hop
        segment = mono[start:start + size]
        if segment.size < size:
            segment = np.pad(segment, (0, size - segment.size))
        power = np.abs(np.fft.rfft(segment * window)) ** 2 / (size * size)
        for row, chosen in enumerate(bins):
            picture[height - 1 - row, column] = float(power[chosen].mean())

    level = 10.0 * np.log10(np.maximum(picture, 1e-30))
    normalised = np.clip((level - floor_db) / (0.0 - floor_db), 0.0, 1.0)
    # A perceptual ramp: dark blue for nothing, through green, to white for loud.
    red = np.clip(normalised * 3.0 - 1.1, 0.0, 1.0)
    green = np.clip(normalised * 2.2 - 0.35, 0.0, 1.0)
    blue = np.clip(np.where(normalised < 0.45, normalised * 1.7,
                            0.77 - (normalised - 0.45) * 0.6 + normalised * 0.8),
                   0.0, 1.0)
    rgb = (np.stack((red, green, blue), axis=2) * 255.0).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def stage_pictures(args) -> dict[str, str]:
    """A spectrogram per mix, and the three stacked for comparison."""
    from PIL import Image, ImageDraw
    from audio import loudness as meter

    os.makedirs(DOCS, exist_ok=True)
    out: dict[str, str] = {}
    images = []
    for variant in VARIANTS:
        samples, rate = meter.read_pcm(wav_path(variant))
        picture = _spectrogram(samples, rate)
        path = os.path.join(DOCS, f"spectrogram_{variant}.png")
        picture.save(path)
        out[variant] = path
        images.append((variant, picture))
        print(f"pictures: {variant:8s} -> {path}")

    gap = 26
    width = images[0][1].width
    stack = Image.new("RGB", (width, sum(i.height + gap for _, i in images) + 14),
                      (16, 16, 20))
    draw = ImageDraw.Draw(stack)
    y = 0
    for label, picture in images:
        draw.text((6, y + 7), f"{label}   40 Hz (bottom) to 16 kHz (top), "
                              f"0 to 19.17 s", fill=(235, 235, 235))
        y += gap
        stack.paste(picture, (0, y))
        y += picture.height
    path = os.path.join(DOCS, "spectrogram_stack.png")
    stack.save(path)
    out["stack"] = path
    print(f"pictures: stack    -> {path}")
    return out


# --- qc ----------------------------------------------------------------------


def stage_qc(args) -> dict[str, Any]:
    """Every acceptance number in the brief, checked against the delivered files."""
    from audio import asmr, loudness as meter

    ffprobe = _tool("ffprobe")
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    # --- Part P, again, against the delivered MP4s --------------------------
    lock = json.load(open(os.path.join(DOCS, "visual_lock.json"), encoding="utf-8"))
    check("video streams identical to V32.1", lock["video_identical"],
          lock["video"]["SOURCE (V32.1)"]["video_stream_md5"])
    check("1150 decoded frames in every film", lock["frames"] == FRAMES,
          str(lock["frames"]))
    check("the three audio masters differ", lock["audio_all_distinct"])

    # --- containers ---------------------------------------------------------
    for variant in VARIANTS:
        path = film_path(variant)
        info = json.loads(_run([ffprobe, "-v", "error", "-show_streams",
                                "-show_format", "-of", "json", path],
                               f"probe {variant}"))
        video = [s for s in info["streams"] if s["codec_type"] == "video"]
        audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
        check(f"{variant}: one video and one audio stream",
              len(video) == 1 and len(audio) == 1)
        check(f"{variant}: 1080x1920 at 60 fps",
              video[0]["width"] == 1080 and video[0]["height"] == 1920
              and video[0]["r_frame_rate"] == "60/1")
        check(f"{variant}: audio at 48 kHz stereo",
              int(audio[0]["sample_rate"]) == 48000 and int(audio[0]["channels"]) == 2)
        duration = float(info["format"]["duration"])
        check(f"{variant}: runtime {duration:.4f} s matches {FRAMES}/{FPS}",
              abs(duration - FRAMES / FPS) < 0.02, f"{duration:.4f}")

    # --- the audio itself ---------------------------------------------------
    for variant in VARIANTS:
        samples, rate = meter.read_pcm(wav_path(variant))
        loud = meter.measure(samples, rate)
        label = f"{variant}"
        check(f"{label}: duration is exactly {FRAMES} frames",
              samples.shape[0] == FRAMES * (rate // FPS), str(samples.shape[0]))
        check(f"{label}: no clipping", loud.sample_peak_dbfs < 0.0,
              f"{loud.sample_peak_dbfs:.2f} dBFS")
        check(f"{label}: true peak at or under {TRUE_PEAK_CEILING_DBTP} dBTP",
              loud.true_peak_dbtp <= TRUE_PEAK_CEILING_DBTP,
              f"{loud.true_peak_dbtp:.2f} dBTP")
        check(f"{label}: within {LUFS_TOLERANCE} LU of {TARGET_LUFS} LUFS",
              abs(loud.integrated_lufs - TARGET_LUFS) <= LUFS_TOLERANCE,
              f"{loud.integrated_lufs:.2f} LUFS")
        check(f"{label}: audio is present throughout",
              float(np.max(np.abs(samples[:rate // 2]))) > 1e-4
              and float(np.max(np.abs(samples[-rate // 2:]))) > 1e-4)
        folded = meter.mono_compatibility(samples, rate)
        check(f"{label}: mono fold-down loses under 1 dB",
              abs(folded["mono_loss_db"]) < 1.0, f"{folded['mono_loss_db']} dB")

    # --- the thing this pass exists to fix ----------------------------------
    for variant in ("A", "B"):
        samples, rate = meter.read_pcm(wav_path(variant))
        control_samples, _ = meter.read_pcm(wav_path("CONTROL"))
        for low, high in ((2000.0, 5000.0), (5000.0, 10000.0)):
            new = meter.continuity(samples, low, high, rate)
            old = meter.continuity(control_samples, low, high, rate)
            band = f"{int(low)}-{int(high)}"
            check(f"{variant}: {band} Hz is no longer a continuous bed",
                  new.within_db < 0.85,
                  f"within 6 dB of median {new.within_db * 100:.1f}% "
                  f"(CONTROL {old.within_db * 100:.1f}%)")
            check(f"{variant}: {band} Hz travels further than CONTROL",
                  new.span_db > old.span_db + 6.0,
                  f"{new.span_db:.1f} dB vs {old.span_db:.1f} dB")
            check(f"{variant}: {band} Hz has quiet stretches",
                  new.quiet_fraction > 0.15,
                  f"{new.quiet_fraction * 100:.1f}% of windows 12 dB down")

    # --- events, alignment, and the shape of the film -----------------------
    replay, track, clock = load()
    telemetry = asmr.telemetry(replay, track, clock)
    mechanisms = asmr.mechanism_hits(replay, track, clock, telemetry)
    recorded = [float(e["t"]) for e in replay["events"]
                if e["kind"] == "mechanism_hit"]
    check("every mechanism cue sits on a recorded hit",
          all(any(abs(cue.at - when) <= 0.005 for when in recorded)
              for cue in mechanisms),
          f"{len(mechanisms)} cues from {len(recorded)} hits")
    modules = {cue.detail["module"] for cue in mechanisms}
    check("all five machines are voiced",
          modules == {"studs", "drum", "sweep", "pair", "last"}, str(sorted(modules)))

    finishes = asmr.crossings(replay, clock)
    winner = next(c for c in finishes if c.detail["order"] == 1)
    check("the finish cue is on the winner's crossing frame",
          abs(winner.at - winner.detail["replay"]) < 0.005,
          f"{winner.at:.4f} s")

    for variant in ("A", "B"):
        detail = json.load(open(os.path.join(DOCS, "masters.json"),
                                encoding="utf-8"))[variant]
        check(f"{variant}: the loudest moment is the winner crossing",
              detail["loudest_moment"]["on_the_crossing"],
              f"{detail['loudest_moment']['second']} s vs "
              f"{detail['loudest_moment']['winner_crossing']} s")
        check(f"{variant}: no finish is buried by the music",
              detail["prominence"]["finishes"]["below_zero"] == 0,
              f"min {detail['prominence']['finishes']['min_db']} dB over the bed")
        check(f"{variant}: the master bus is not compressed",
              detail["compressor_reduction_db"] == 0.0)
        check(f"{variant}: the limiter is a safety, not a level control",
              detail["limiter_worst_db"] > -3.0 and detail["limiter_mean_db"] > -0.2,
              f"worst {detail['limiter_worst_db']} dB, "
              f"mean {detail['limiter_mean_db']} dB")

    failed = [row for row in checks if not row["pass"]]
    report = {"checks": checks, "passed": len(checks) - len(failed),
              "failed": len(failed), "total": len(checks)}
    _write_json(os.path.join(DOCS, "qc.json"), report)

    for row in checks:
        mark = "ok  " if row["pass"] else "FAIL"
        print(f"  {mark} {row['check']}" + (f"  [{row['detail']}]" if row["detail"] else ""))
    print(f"qc: {report['passed']}/{report['total']} checks passed")
    if failed:
        raise AudioError(f"{len(failed)} QC check(s) failed")
    return report


# --- winner ------------------------------------------------------------------


def stage_winner(args) -> str:
    """Copy the chosen mix to the upload-candidate path."""
    choice = args.winner
    source = film_path(choice)
    if not os.path.isfile(source):
        raise AudioError(f"missing {source}; run `mux` first")
    os.makedirs(EXPORT, exist_ok=True)
    target = os.path.join(EXPORT, "race2_switchyard_final_audio.mp4")
    shutil.copyfile(source, target)
    phone_source = os.path.join(
        EXPORT, f"race2_{COURSE}_{choice.lower()}_phone_270x480.mp4")
    if os.path.isfile(phone_source):
        shutil.copyfile(phone_source, os.path.join(
            EXPORT, "race2_switchyard_final_audio_phone_270x480.mp4"))
    print(f"winner: Mix {choice} -> {target}")
    return target


STAGES = {
    "diagnose": stage_diagnose,
    "build": stage_build,
    "mux": stage_mux,
    "lock": stage_lock,
    "compare": stage_compare,
    "report": stage_report,
    "pictures": stage_pictures,
    "qc": stage_qc,
    "winner": stage_winner,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=tuple(STAGES) + ("all",))
    parser.add_argument("--winner", default="B", choices=("A", "B", "CONTROL"))
    args = parser.parse_args(argv)

    os.chdir(REPO)
    for folder in (OUT, WORK, DOCS, EXPORT):
        os.makedirs(folder, exist_ok=True)

    order = ("build", "diagnose", "mux", "lock", "compare", "report", "pictures",
             "qc", "winner")
    todo = order if args.stage == "all" else (args.stage,)
    for name in todo:
        print(f"--- {name} " + "-" * (70 - len(name)))
        STAGES[name](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

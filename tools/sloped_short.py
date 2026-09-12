"""V19 plus a hook, a soundtrack and three marks: the deliverable Short.

    python tools/sloped_short.py --seed 5432

**The master is an input, not something this rebuilds.** V19 is locked: its
physics, replay, edit map and camera poses are all fixed, and nothing here opens
Godot. The film is made by holding V19's first frame for 42 frames, laying three
overlays on top and muxing a soundtrack synthesised from the same replay the
pictures came from.

Two files come out, because overlays and sound are separable decisions:

    real_race_v20.mp4          the Short: overlays, audio
    real_race_v20_visual.mp4   the same picture with no audio track

Stages:

    audio     synthesise the soundtrack from the replay, write a WAV
    overlays  draw the PNGs, and the winner ring's frame sequence
    mux       hold, composite, encode both files
    qc        measure the result against the brief
    all       all four

## Why the hold is 42 frames rather than 0.7 seconds

Because 0.7 s is not a whole number of frames at every rate anybody might try,
and a fractional hold makes `tpad` round somewhere this code cannot see. 42 at
60 fps is exactly 0.7 s, the audio is built to `Clock.duration` which is derived
from the same integer, and the finished file is 1192 frames - which `qc` checks
rather than assumes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from audio import marble
from audio.synthesis import SAMPLE_RATE
from audio.wav_io import write_wav
from sloped import overlays, presentation

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK_DIR = os.path.join(OUT_DIR, "short")
MASTER = os.path.join(OUT_DIR, "real_race_v19.mp4")
VIDEO = os.path.join(OUT_DIR, "real_race_v20.mp4")
VISUAL = os.path.join(OUT_DIR, "real_race_v20_visual.mp4")

WIDTH, HEIGHT, FPS = 1080, 1920, 60
VIDEO_CRF = 17
VIDEO_PRESET = "slow"
AUDIO_BITRATE = "256k"

# The hook is on screen for the hold plus a beat, and gone before the gates
# move. `presentation.actuator_move` puts the paddles at output 0.817, so the
# fade ends at 0.80 and the picture is clean by the time anything happens.
PICK_ONE_IN = 0.10
PICK_ONE_OUT_FROM = 0.62
PICK_ONE_OUT_TO = 0.80

# The winner's mark. It starts 0.20 s after the crossing - "after the winner
# clearly crosses" - and runs 0.70 s, which ends 0.88 s before the fourth and
# fifth arrive together, so it cannot be on screen during the close finish.
WINNER_DELAY = 0.20
WINNER_SECONDS = 0.70

# One fact, at the end. 0.65 s, finishing with the film.
END_FACT_SECONDS = 0.65


class ShortError(RuntimeError):
    pass


def _run(command: Sequence[str], label: str) -> None:
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-20:])
        raise ShortError(f"{label}: exited {done.returncode}\n{tail}")


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise ShortError("ffmpeg is not on PATH")
    return found


def _probe(path: str) -> dict[str, Any]:
    found = shutil.which("ffprobe")
    if found is None:
        raise ShortError("ffprobe is not on PATH")
    done = subprocess.run(
        [found, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        raise ShortError(f"ffprobe failed on {path}")
    return json.loads(done.stdout)


def master_frames(path: str) -> int:
    for stream in _probe(path)["streams"]:
        if stream.get("codec_type") == "video":
            return int(stream["nb_frames"])
    raise ShortError(f"{path} has no video stream")


def load_all(seed: int):
    replay_path = os.path.join(OUT_DIR, f"race_{seed}.json")
    track_path = os.path.join(OUT_DIR, f"cameras_{seed}.json")
    for path in (replay_path, track_path, MASTER):
        if not os.path.isfile(path):
            raise ShortError(f"missing input: {path}")
    return presentation.load(replay_path, track_path, master_frames(MASTER))


# --- stages -----------------------------------------------------------------


def stage_audio(seed: int) -> str:
    replay, track, clock = load_all(seed)
    mix = marble.build_race_audio(replay, track, clock)
    os.makedirs(WORK_DIR, exist_ok=True)
    path = os.path.join(WORK_DIR, f"race_{seed}.wav")
    write_wav(path, mix.left, mix.right, sample_rate=mix.sample_rate)
    print(f"audio: {mix.seconds:.4f} s, {len(mix.left)} samples at {mix.sample_rate} Hz")
    print(f"  placed {mix.placed}")
    print(
        f"  peak in {20 * math.log10(max(mix.peak_before, 1e-9)):.2f} dBFS, "
        f"compressor {mix.gain_reduction_db:.2f} dB, "
        f"out {20 * math.log10(max(mix.peak_after, 1e-9)):.2f} dBFS, "
        f"limiter {'engaged' if mix.limited else 'idle'}"
    )
    print(f"  wrote {path}")
    return path


def stage_overlays(seed: int) -> dict[str, Any]:
    replay, track, clock = load_all(seed)
    os.makedirs(WORK_DIR, exist_ok=True)

    hook = os.path.join(WORK_DIR, "pick_one.png")
    overlays.pick_one().save(hook)
    fact = os.path.join(WORK_DIR, "end_fact.png")
    overlays.end_fact().save(fact)

    winner, crossed = _winner_of(replay)
    start = clock.at(crossed)
    if start is None:
        raise ShortError("the winner's crossing is not in the film")
    start += WINNER_DELAY
    ring_dir = os.path.join(WORK_DIR, "ring")
    if os.path.isdir(ring_dir):
        shutil.rmtree(ring_dir)
    os.makedirs(ring_dir, exist_ok=True)

    where = dict(
        (round(row[0], 6), row[1:])
        for row in presentation.screen_track(
            replay, track, clock, winner, (start - 0.05, start + WINNER_SECONDS + 0.05)
        )
    )
    times = sorted(where)
    count = int(round(WINNER_SECONDS * FPS))
    written = 0
    for index in range(count):
        when = start + index / FPS
        nearest = min(times, key=lambda value: abs(value - when)) if times else None
        if nearest is None:
            continue
        x, y, radius = where[nearest]
        image = overlays.winner_ring(x, y, radius, index / max(1, count - 1))
        image.save(os.path.join(ring_dir, f"ring_{index:04d}.png"))
        written += 1

    print(f"overlays: hook {hook}")
    print(f"          fact {fact}")
    print(f"          ring {written} frames from {start:.3f} s on marble {winner}")
    return {
        "hook": hook,
        "fact": fact,
        "ring_dir": ring_dir,
        "ring_from": start,
        "ring_frames": written,
        "winner": winner,
        "duration": clock.duration,
        "hold": clock.hold,
        "frames": clock.frames,
    }


def _winner_of(replay: dict[str, Any]) -> tuple[int, float]:
    for event in replay["events"]:
        if event["kind"] == "finish_line" and int(event["order"]) == 1:
            return int(event["id"]), float(event["t"])
    raise ShortError("the replay records no winner")


def stage_mux(seed: int, plan: dict[str, Any], audio_path: str) -> dict[str, str]:
    hold = plan["hold"]
    ring_from = plan["ring_from"]
    ring_seconds = plan["ring_frames"] / FPS
    fact_from = plan["duration"] - END_FACT_SECONDS

    graph = (
        f"[0:v]tpad=start_duration={hold}:start_mode=clone,setpts=PTS-STARTPTS[base];"
        f"[1:v]format=rgba,fade=t=in:st={PICK_ONE_IN}:d=0.18:alpha=1,"
        f"fade=t=out:st={PICK_ONE_OUT_FROM}:d={PICK_ONE_OUT_TO - PICK_ONE_OUT_FROM}:alpha=1[hook];"
        f"[base][hook]overlay=0:0:enable='between(t,0,{PICK_ONE_OUT_TO})'[v1];"
        f"[2:v]format=rgba,setpts=PTS-STARTPTS+{ring_from}/TB[ring];"
        f"[v1][ring]overlay=0:0:enable='between(t,{ring_from},{ring_from + ring_seconds})'[v2];"
        f"[3:v]format=rgba,fade=t=in:st=0:d=0.20:alpha=1[fact];"
        f"[v2][fact]overlay=0:0:enable='between(t,{fact_from},{plan['duration']})'[vout]"
    )

    common = [
        _ffmpeg(), "-y",
        "-i", MASTER,
        "-loop", "1", "-framerate", str(FPS), "-i", plan["hook"],
        "-framerate", str(FPS), "-start_number", "0",
        "-i", os.path.join(plan["ring_dir"], "ring_%04d.png"),
        "-loop", "1", "-framerate", str(FPS), "-i", plan["fact"],
    ]
    encode = [
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-frames:v", str(plan["frames"]),
    ]

    os.makedirs(os.path.dirname(os.path.abspath(VISUAL)), exist_ok=True)
    _run(common + ["-filter_complex", graph, "-map", "[vout]", "-an", *encode, VISUAL],
         "encode the silent visual cut")
    _run(
        common + ["-i", audio_path, "-filter_complex", graph, "-map", "[vout]",
                  "-map", "4:a", *encode,
                  "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(SAMPLE_RATE),
                  "-shortest", VIDEO],
        "encode the Short",
    )
    for path in (VISUAL, VIDEO):
        print(f"video: {path}  {os.path.getsize(path) / (1024 * 1024):.1f} MiB")
    return {"video": VIDEO, "visual": VISUAL}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument(
        "--stage", default="all", choices=("audio", "overlays", "mux", "qc", "all")
    )
    args = parser.parse_args(argv)

    stages = ("audio", "overlays", "mux", "qc") if args.stage == "all" else (args.stage,)
    audio_path = os.path.join(WORK_DIR, f"race_{args.seed}.wav")
    plan: dict[str, Any] | None = None
    for stage in stages:
        print(f"--- {stage} ---")
        if stage == "audio":
            audio_path = stage_audio(args.seed)
        elif stage == "overlays":
            plan = stage_overlays(args.seed)
        elif stage == "mux":
            if plan is None:
                plan = stage_overlays(args.seed)
            stage_mux(args.seed, plan, audio_path)
        elif stage == "qc":
            from tools.sloped_short_qc import report
            if report(args.seed) is False:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

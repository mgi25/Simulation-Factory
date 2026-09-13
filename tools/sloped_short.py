"""A silent master plus a hook, a soundtrack and three marks: the Short.

    python tools/sloped_short.py --seed 5432

**The master is an input, not something this rebuilds.** The physics, the seed,
the replay and the edit map are locked, and nothing here opens Godot. The film
is made by holding the master's first frame for 42 frames, cutting 85 frames out
of the middle of the start, laying three overlays on top and muxing a soundtrack
synthesised from the same replay the pictures came from.

Which master is an edition's own choice. `v20` and `v211` are cut from
`real_race_v19.mp4`; `v21`, the deliverable, is cut from
`real_race_v21_master.mp4` - the same replay and the same edit map rendered
through the V21.2 camera track and the V21 contrast pass. See MASTER_V21.

Two files come out, because overlays and sound are separable decisions:

    real_race_v21.mp4          the Short: overlays, audio
    real_race_v21_visual.mp4   the same picture with no audio track

## V21.1: the start pass

V20 spent 4.02 s of its 19.87 inside the start mechanism and did not put the
field on the downhill until 4.98 s. A viewer who has already chosen a marble by
0.7 s then has nothing to watch for four seconds, which is where a Short loses
them.

V21.1 takes a further **85 whole frames** out of the middle of the start shot -
the only honest way a master that is already rendered can omit more time - and
V20's two start windows become one:

    output 0.00-0.70  the held first frame, PICK ONE
    output 0.70-1.50  replay 0.200-1.000: the gates open at 0.817 and the
                      eight pour out of their bays and tumble together
    output 1.50       the cut, 4.833 s of drum omitted, one whoosh
    output 1.50-2.60  replay 5.833-7.620: the settled field, the floor drops
                      at 1.80, and they are away down the mountain

Nothing is sped up or slowed down, nothing is interpolated, no frame repeats and
no frame runs backwards - `presentation.omit_frames` refuses a cut that does not
step forwards, and `tests/test_sloped_retention.py` pins the rest.
`--edition v20` still builds V20, and `--edition v211` the retention pass's
own proof, from V19's master.

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

# --- the masters ------------------------------------------------------------
#
# Two silent masters, both of the same locked replay of seed 5432 and both cut
# to the same edit map, so they are frame for frame the same instants of the
# same race. They differ only in the lens and the light:
#
#   V19     the shipped camera track, the V20 grade. What V20 and V21.1 are
#           cut from, and it is kept so both of them still rebuild.
#   V21     the V21.2 camera track (`cameras.EDITS["v212"]`) under the V21
#           contrast pass (`lab_palette.new("tower", "v21")`, which is the race
#           scene's own default). What the delivered V21 is cut from.
#
# The integrated master is a *render*, not a re-encode of anything: it comes out
# of `tools/sloped_integrate.py --stage clip` against `cameras_5432.json` solved
# with `--edit v212`. Combining two finished films in ffmpeg would have given a
# picture neither pass ever measured.
MASTER_V19 = os.path.join(OUT_DIR, "real_race_v19.mp4")
MASTER_V21 = os.path.join(OUT_DIR, "real_race_v21_master.mp4")

# Kept for the callers and the tests that name the locked V19 master directly.
MASTER = MASTER_V19

# --- the editions -----------------------------------------------------------
#
# One machine, two masters, two cuts. V20 keeps every frame of V19's master;
# the retention cut drops master frames 49 to 133 inclusive - the tail of the
# drum in the first start window and the head of the second - so the join is
# master frame 48 (replay 1.000) to master frame 134 (replay 5.833333) on the
# same lens, and everything after it lands 85 frames earlier.
#
# `v211` applies that cut to V19's master, which is exactly the film the
# retention pass delivered and is kept so its result still reproduces. `v21`
# applies the same cut to the integrated master, and is the deliverable: the
# same edit over the V21.2 lenses and the V21 grade.

EDITIONS: dict[str, dict[str, Any]] = {
    "v20": {
        "master": MASTER_V19,
        "cuts": (),
        "video": os.path.join(OUT_DIR, "real_race_v20.mp4"),
        "visual": os.path.join(OUT_DIR, "real_race_v20_visual.mp4"),
        "runtime": (19.8, 20.2),
    },
    "v211": {
        "master": MASTER_V19,
        "cuts": ((49, 133),),
        "video": os.path.join(OUT_DIR, "real_race_v211.mp4"),
        "visual": os.path.join(OUT_DIR, "real_race_v211_visual.mp4"),
        "runtime": (18.2, 18.7),
    },
    "v21": {
        "master": MASTER_V21,
        "cuts": ((49, 133),),
        "video": os.path.join(OUT_DIR, "real_race_v21.mp4"),
        "visual": os.path.join(OUT_DIR, "real_race_v21_visual.mp4"),
        "runtime": (18.2, 18.7),
    },
}
DEFAULT_EDITION = "v21"

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


def load_all(seed: int, edition: str = DEFAULT_EDITION):
    """The replay, the camera track, the clock, and the master frames to keep.

    The clock is the one the finished file runs on, so every cue and every mark
    is placed through this edition's own map rather than V19's.
    """
    if edition not in EDITIONS:
        raise ShortError(f"no such edition: {edition!r}; try {sorted(EDITIONS)}")
    replay_path = os.path.join(OUT_DIR, f"race_{seed}.json")
    track_path = os.path.join(OUT_DIR, f"cameras_{seed}.json")
    master = EDITIONS[edition]["master"]
    for path in (replay_path, track_path, master):
        if not os.path.isfile(path):
            raise ShortError(f"missing input: {path}")
    replay, track, clock = presentation.load(
        replay_path, track_path, master_frames(master)
    )
    clock, keep = presentation.omit_frames(clock, EDITIONS[edition]["cuts"])
    return replay, track, clock, keep


def _select(cuts: Sequence[tuple[int, int]]) -> str:
    """The filter that takes whole frames out of the master, or nothing at all.

    `select` decides frame by frame on the master's own frame number, so the cut
    lands where the map says it does; `setpts=N/FRAME_RATE/TB` closes the gap by
    renumbering what survives. Neither filter touches a frame's content and
    neither can reorder or repeat one.
    """
    if not cuts:
        return ""
    gone = "+".join(f"between(n,{first},{last})" for first, last in cuts)
    return f"select='not({gone})',setpts=N/FRAME_RATE/TB,"


# --- stages -----------------------------------------------------------------


def stage_audio(seed: int, edition: str = DEFAULT_EDITION) -> str:
    replay, track, clock, _keep = load_all(seed, edition)
    mix = marble.build_race_audio(replay, track, clock)
    os.makedirs(WORK_DIR, exist_ok=True)
    path = os.path.join(WORK_DIR, f"race_{seed}_{edition}.wav")
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


def stage_overlays(seed: int, edition: str = DEFAULT_EDITION) -> dict[str, Any]:
    replay, track, clock, keep = load_all(seed, edition)
    os.makedirs(WORK_DIR, exist_ok=True)

    winner, crossed = _winner_of(replay)

    hook = os.path.join(WORK_DIR, "pick_one.png")
    overlays.pick_one().save(hook)
    # The end card carries the winning marble's own hue, read out of the replay
    # rather than typed, so a different seed would carry a different ball.
    fact = os.path.join(WORK_DIR, f"end_fact_{winner}.png")
    overlays.end_fact(accent=overlays.MARBLE_HUES[winner]).save(fact)

    start = clock.at(crossed)
    if start is None:
        raise ShortError("the winner's crossing is not in the film")
    # **Snapped to a frame, so the mark opens on the frame it is placed on.**
    # `ring_from` becomes an ffmpeg `setpts` offset in the ring stream's own
    # 1/60 timebase; an offset that is not a whole number of ticks lands the
    # sequence between two frames and the first one is never composited. That
    # is the frame the flash exists for, and measured on the file it was the
    # frame that went missing.
    start = round((start + WINNER_DELAY) * FPS) / FPS
    ring_dir = os.path.join(WORK_DIR, f"ring_{edition}")
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
        "edition": edition,
        "master": EDITIONS[edition]["master"],
        "cuts": EDITIONS[edition]["cuts"],
        "keep": keep,
        "video": EDITIONS[edition]["video"],
        "visual": EDITIONS[edition]["visual"],
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

    video = plan["video"]
    visual = plan["visual"]
    graph = (
        f"[0:v]{_select(plan['cuts'])}"
        f"tpad=start_duration={hold}:start_mode=clone,setpts=PTS-STARTPTS[base];"
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
        "-i", plan["master"],
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

    os.makedirs(os.path.dirname(os.path.abspath(visual)), exist_ok=True)
    _run(common + ["-filter_complex", graph, "-map", "[vout]", "-an", *encode, visual],
         "encode the silent visual cut")
    _run(
        common + ["-i", audio_path, "-filter_complex", graph, "-map", "[vout]",
                  "-map", "4:a", *encode,
                  "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(SAMPLE_RATE),
                  "-shortest", video],
        "encode the Short",
    )
    for path in (visual, video):
        print(f"video: {path}  {os.path.getsize(path) / (1024 * 1024):.1f} MiB")
    return {"video": video, "visual": visual}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument(
        "--stage", default="all", choices=("audio", "overlays", "mux", "qc", "all")
    )
    parser.add_argument(
        "--edition", default=DEFAULT_EDITION, choices=tuple(EDITIONS),
        help="v21 is the start/retention cut; v20 rebuilds the earlier one",
    )
    args = parser.parse_args(argv)

    stages = ("audio", "overlays", "mux", "qc") if args.stage == "all" else (args.stage,)
    audio_path = os.path.join(WORK_DIR, f"race_{args.seed}_{args.edition}.wav")
    plan: dict[str, Any] | None = None
    for stage in stages:
        print(f"--- {stage} ---")
        if stage == "audio":
            audio_path = stage_audio(args.seed, args.edition)
        elif stage == "overlays":
            plan = stage_overlays(args.seed, args.edition)
        elif stage == "mux":
            if plan is None:
                plan = stage_overlays(args.seed, args.edition)
            stage_mux(args.seed, plan, audio_path)
        elif stage == "qc":
            from tools.sloped_short_qc import report
            if report(args.seed, args.edition) is False:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

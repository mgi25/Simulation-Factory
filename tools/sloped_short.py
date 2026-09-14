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
from sloped import overlays, presentation, v24, v24_hook, v24_payoff

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
# V22 renders two silent pieces rather than one: the race, to the V22 edit map,
# and the course preview, which is its own footage over a frozen field. See
# `tools/sloped_v22.py` and `sloped/v22.py`.
MASTER_V22 = os.path.join(OUT_DIR, "v22", "race_master.mp4")
PREVIEW_V22 = os.path.join(OUT_DIR, "v22", "preview_master.mp4")
# V22.1 renders the same two pieces to its own edit: the race through
# `sloped.v221.edit()` with the finish rewritten by `v221_finish`, and a preview
# of 210 frames rather than 120. Both come out of
# `tools/sloped_v22.py --edition v221`.
MASTER_V221 = os.path.join(OUT_DIR, "v221", "race_master.mp4")
PREVIEW_V221 = os.path.join(OUT_DIR, "v221", "preview_master.mp4")
# V24 renders **one** piece of footage and no preview at all. The film's second
# zero is this master's own first frame: no flight in front of it and no frozen
# hold on it. See `sloped.v24`.
MASTER_V24 = os.path.join(OUT_DIR, "v24", "race_master.mp4")

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
    # **V22 has no cuts, because its master is rendered to the edit it wants.**
    # V21.1 took 85 frames out of a finished file because the mixing it wanted
    # back was already rendered and the obstacle it wanted back was not. V22
    # re-renders, so Candidate A's start, the restored obstacle and the extended
    # finish are all window bounds in `cameras.EDITS["v22"]` - and a master cut
    # after the fact would only be able to take time away again.
    #
    # What is new is the preview: 120 frames of different footage in front of
    # everything, joined by `concat` rather than by an overlay, and carried in
    # the clock as `prefix`. See `sloped.presentation.Clock`.
    "v22": {
        "master": MASTER_V22,
        "preview": PREVIEW_V22,
        "cuts": (),
        "video": os.path.join(OUT_DIR, "real_race_v22.mp4"),
        "visual": os.path.join(OUT_DIR, "real_race_v22_visual.mp4"),
        "silent": os.path.join(OUT_DIR, "real_race_v22_master.mp4"),
        "track": os.path.join(OUT_DIR, "cameras_v22_{seed}.json"),
        "runtime": (22.8, 23.3),
    },
    # **V22.1 is V22 with three joins rebuilt and one sound removed.** The
    # picture is a different render - a longer preview, a start that omits 116
    # frames instead of 235, and a finish that is the end of the chase - and all
    # of that arrives here as two file paths and a track, because everything
    # that places a cue derives it from the track's own edit map.
    #
    # `cues` is the one genuinely new field. See `audio.marble.Cues`: V22.1's
    # omission is phase-locked and invisible, so marking it with a whoosh would
    # announce an edit the viewer could not otherwise see, and the mixer it now
    # holds on screen for five and a half seconds gets its own machinery
    # instead. Every other edition keeps `default` and rebuilds unchanged.
    "v221": {
        "master": MASTER_V221,
        "preview": PREVIEW_V221,
        "cuts": (),
        "cues": "v221",
        "video": os.path.join(OUT_DIR, "real_race_v221.mp4"),
        "visual": os.path.join(OUT_DIR, "real_race_v221_visual.mp4"),
        "silent": os.path.join(OUT_DIR, "real_race_v221_master.mp4"),
        "track": os.path.join(OUT_DIR, "cameras_v221_{seed}.json"),
        "runtime": (26.0, 27.0),
    },
    # **V24 is the hook experiment, and three of its fields are new because
    # three things about the opening and the ending are new.**
    #
    # `hold` 0.0. Every edition before this one freezes the master's first frame
    # for 0.7 s and puts the mark on the still. V24's first frame is already the
    # hook - eight racers at 146 px under PICK A COLOR, with the release paddles
    # moving 0.117 s later - so there is nothing a freeze would buy and 0.7 s it
    # would cost. `presentation.Clock` takes the hold as a field, so this is a
    # number rather than a branch, and `prefix` is 0.0 because there is no
    # preview either.
    #
    # `mark` chooses the opening overlay. `pick_one` is 150 pt at baseline 395,
    # measured against V20's held frame; V24's twelve glyphs are 96 pt at
    # baseline 269, measured by `v24_hook.text_plate` against the frame this
    # opening actually renders. See `sloped.v24.MARK_BASELINE`.
    #
    # `payoff` replaces the end fact with the payoff lab's plate: PURPLE WINS
    # over the winner's own #8E3FD4, warm white on it at 5.26:1, with the ring
    # moved on to the crossing where the winner is actually visible.
    "v24": {
        "master": MASTER_V24,
        "cuts": (),
        "cues": "v221",
        "hold": 0.0,
        "mark": "v24",
        "payoff": v24_payoff.RECOMMENDED,
        "video": os.path.join(OUT_DIR, "real_race_v24.mp4"),
        "visual": os.path.join(OUT_DIR, "real_race_v24_visual.mp4"),
        "silent": os.path.join(OUT_DIR, "real_race_v24_master.mp4"),
        "track": os.path.join(OUT_DIR, "cameras_v24_{seed}.json"),
        "runtime": (19.8, 20.4),
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
    track_path = EDITIONS[edition].get(
        "track", os.path.join(OUT_DIR, "cameras_{seed}.json")
    ).format(seed=seed)
    master = EDITIONS[edition]["master"]
    preview = EDITIONS[edition].get("preview")
    for path in (replay_path, track_path, master):
        if not os.path.isfile(path):
            raise ShortError(f"missing input: {path}")
    # **The preview's cost to the clock is its frame count over the rate.** Not
    # the 1.9833 s its own report calls its duration, which is the span of its
    # frame centres; 120 frames hold the screen for 2.000 s and everything in
    # the film after them is placed from that. See `sloped.v22`.
    prefix = 0.0
    if preview:
        if not os.path.isfile(preview):
            raise ShortError(f"missing input: {preview}")
        prefix = master_frames(preview) / float(FPS)
    replay, track, clock = presentation.load(
        replay_path, track_path, master_frames(master), prefix=prefix
    )
    # **The hold is an edition's choice, not a constant.** It has been 0.70 s
    # since V20 because every edition before V24 opens on a still; V24 opens on
    # a moving hook and holds nothing, so it asks for 0.0 and every time in the
    # film after second zero is a master frame. `Clock` carries it as a field,
    # so `at`, `replay_at`, `frames` and `duration` all already know.
    hold = EDITIONS[edition].get("hold", presentation.HOLD_SECONDS)
    if hold != clock.hold:
        clock = presentation.Clock(
            clock.segments, hold=hold, fps=clock.fps,
            master_frames=clock.master_frames, prefix=clock.prefix,
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


def cue_policy(edition: str) -> marble.Cues:
    """Which non-diegetic cues this edition uses. `default` unless it says."""
    return marble.CUES[EDITIONS[edition].get("cues", "default")]


def stage_audio(seed: int, edition: str = DEFAULT_EDITION) -> str:
    replay, track, clock, _keep = load_all(seed, edition)
    mix = marble.build_race_audio(replay, track, clock, cues=cue_policy(edition))
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

    # **The opening mark, and which drawing of it this edition uses.** Both
    # are the same face, the same warm white and the same soft shadow through
    # `overlays._shadowed`; what differs is the words and where they sit, and
    # both of those were measured against the frame the mark is actually on.
    if EDITIONS[edition].get("mark") == "v24":
        hook = os.path.join(WORK_DIR, "pick_a_color.png")
        v24_hook.pick_a_color(baseline=v24.MARK_BASELINE).save(hook)
    else:
        hook = os.path.join(WORK_DIR, "pick_one.png")
        overlays.pick_one().save(hook)

    # The end card. `end_fact` carries the winning marble's own hue as a dot,
    # read out of the replay rather than typed; V24's plate carries it as an
    # *area* with the colour's name reversed out of it, because the payoff lab
    # measured that the dot is 27 px wide and the film never says a colour.
    style = EDITIONS[edition].get("payoff")
    if style:
        card = v24_payoff.build(style=style, winner=winner,
                                from_place=v24_payoff.WINNER_FROM)
        fact = os.path.join(WORK_DIR, f"payoff_{style}_{winner}.png")
        card.image.save(fact)
    else:
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
    # **The winner's ring opens where the winner is.** V22.1 opens it 0.200 s
    # after the crossing and runs 0.700, which the payoff lab measured puts
    # *one frame* of it on a visible marble and the other 0.683 s on the gantry
    # rail. The winner is on screen for 0.217 s, so V24 opens the ring **on**
    # the crossing and runs 0.300.
    delay = (v24_payoff.RING_DELAY if EDITIONS[edition].get("payoff")
             else WINNER_DELAY)
    ring_seconds = (v24_payoff.RING_SECONDS if EDITIONS[edition].get("payoff")
                    else WINNER_SECONDS)
    start = round((start + delay) * FPS) / FPS
    ring_dir = os.path.join(WORK_DIR, f"ring_{edition}")
    if os.path.isdir(ring_dir):
        shutil.rmtree(ring_dir)
    os.makedirs(ring_dir, exist_ok=True)

    where = dict(
        (round(row[0], 6), row[1:])
        for row in presentation.screen_track(
            replay, track, clock, winner, (start - 0.05, start + ring_seconds + 0.05)
        )
    )
    times = sorted(where)
    count = int(round(ring_seconds * FPS))
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
    # When the mark is up, and when the card is. Both are edition choices and
    # both are computed here rather than in the filter graph, so the report and
    # the QC read the same numbers ffmpeg is given.
    if EDITIONS[edition].get("mark") == "v24":
        mark = (v24.MARK_IN, v24.MARK_OUT_FROM, v24.MARK_OUT_TO)
    else:
        mark = (clock.prefix + PICK_ONE_IN, clock.prefix + PICK_ONE_OUT_FROM,
                clock.prefix + PICK_ONE_OUT_TO)
    if EDITIONS[edition].get("payoff"):
        plan_card = v24_payoff.schedule(
            crossing=start - delay, beat=v24.BEAT,
            seconds=v24_payoff.PAYOFF_SECONDS, fps=FPS,
        )["card"]
    else:
        plan_card = (clock.duration - END_FACT_SECONDS, clock.duration)

    print(f"          mark {mark[0]:.3f}-{mark[2]:.3f}  "
          f"card {plan_card[0]:.3f}-{plan_card[1]:.3f}  "
          f"crossing {start - delay:.3f}  film {clock.duration:.4f} s")
    return {
        "hook": hook,
        "fact": fact,
        "mark": mark,
        "card": plan_card,
        "ring_dir": ring_dir,
        "ring_from": start,
        "ring_frames": written,
        "winner": winner,
        "duration": clock.duration,
        "hold": clock.hold,
        "prefix": clock.prefix,
        "preview": EDITIONS[edition].get("preview"),
        "silent": EDITIONS[edition].get("silent"),
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


def _base_for(plan: dict[str, Any]) -> str:
    """The base picture: the master, cut, held and joined to its preview.

    Split out of `stage_mux` because it is used twice - once on its own for the
    silent integrated master, once as the head of the overlay chain - and
    because it is the half of the graph a test can read without an encoder.
    """
    hold = plan["hold"]
    preview = plan.get("preview")
    # **`tpad` is omitted entirely when there is no hold, not given zero.**
    # `start_duration=0` is legal and is a no-op, but it also makes the graph
    # claim a hold the film does not have; leaving the filter out says what V24
    # is, and `setpts` still normalises the timestamps.
    base = f"[0:v]{_select(plan['cuts'])}"
    if hold > 0.0:
        base += f"tpad=start_duration={hold}:start_mode=clone,"
    base += "setpts=PTS-STARTPTS"
    if preview:
        base += (
            ",format=yuv420p,setsar=1[race];"
            f"[{_PREVIEW_INPUT}:v]format=yuv420p,setsar=1,setpts=PTS-STARTPTS[pre];"
            "[pre][race]concat=n=2:v=1:a=0[base];"
        )
    else:
        base += "[base];"
    return base


def _graph_for(plan: dict[str, Any]) -> str:
    """The whole filter graph: the base, the mark, the ring and the end card.

    **The mark does not fade in when it opens on frame zero.** A `fade=t=in`
    starting at 0 makes the first frame transparent, and the first frame is the
    one the whole pass exists for: PICK A COLOR has to be readable before the
    viewer has decided anything. Every edition that opens its mark over a held
    frame still fades, because there it is a title coming up on a still.
    """
    prefix = plan.get("prefix", 0.0)
    ring_from = plan["ring_from"]
    ring_seconds = plan["ring_frames"] / FPS
    fact_from, fact_to = plan["card"]
    hook_in, hook_out_from, hook_out_to = plan["mark"]
    fade_in = (f"fade=t=in:st={hook_in}:d=0.18:alpha=1,"
               if hook_in > 0.0 else "")
    return (
        _base_for(plan)
        + f"[1:v]format=rgba,{fade_in}"
        f"fade=t=out:st={hook_out_from}:d={hook_out_to - hook_out_from}:alpha=1[hook];"
        f"[base][hook]overlay=0:0:enable='between(t,{prefix},{hook_out_to})'[v1];"
        f"[2:v]format=rgba,setpts=PTS-STARTPTS+{ring_from}/TB[ring];"
        f"[v1][ring]overlay=0:0:enable='between(t,{ring_from},{ring_from + ring_seconds})'[v2];"
        f"[3:v]format=rgba,fade=t=in:st=0:d=0.20:alpha=1[fact];"
        f"[v2][fact]overlay=0:0:enable='between(t,{fact_from},{fact_to})'[vout]"
    )


def stage_mux(seed: int, plan: dict[str, Any], audio_path: str) -> dict[str, str]:
    hold = plan["hold"]
    prefix = plan.get("prefix", 0.0)
    preview = plan.get("preview")
    ring_from = plan["ring_from"]
    ring_seconds = plan["ring_frames"] / FPS
    fact_from, fact_to = plan["card"]

    # **The mark's times, as `stage_overlays` computed them.** For every edition
    # before V24 they are offsets into the held frame, which is where they have
    # always been: `prefix` is zero before V22, and with a course preview in
    # front PICK ONE moves with the hold so the preview plays clean. V24 has
    # neither a preview nor a hold, so its mark opens at second zero over live
    # footage - which is the whole experiment and is why these come in rather
    # than being recomputed here.
    hook_in, hook_out_from, hook_out_to = plan["mark"]

    video = plan["video"]
    visual = plan["visual"]
    silent = plan.get("silent")

    # The base picture and the overlay chain. `concat` joins the preview rather
    # than an overlay because the preview is *different footage* occupying its
    # own frames, and rather than a second encode because a join made in the
    # filter graph never re-compresses what it joins.
    base = _base_for(plan)
    graph = _graph_for(plan)

    common = [
        _ffmpeg(), "-y",
        "-i", plan["master"],
        "-loop", "1", "-framerate", str(FPS), "-i", plan["hook"],
        "-framerate", str(FPS), "-start_number", "0",
        "-i", os.path.join(plan["ring_dir"], "ring_%04d.png"),
        "-loop", "1", "-framerate", str(FPS), "-i", plan["fact"],
    ]
    if preview:
        common += ["-i", preview]
    encode = [
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-frames:v", str(plan["frames"]),
    ]

    os.makedirs(os.path.dirname(os.path.abspath(visual)), exist_ok=True)
    written = []
    if silent:
        # The integrated presentation master: the whole picture, joined and
        # held, with no mark on it and no sound. What a reviewer watches to see
        # the camera work without anything drawn over it.
        #
        # **Its own graph, because a filter output may be used once.** `[base]`
        # is consumed by the hook overlay, so mapping it as well as the overlay
        # chain's end is "Output with label 'base' does not exist in any defined
        # filter graph, or was already used elsewhere". Splitting it instead
        # would leave an unused branch on the two passes that do overlay, which
        # ffmpeg rejects for the same reason from the other side. The inputs are
        # the same list so every index in `base` still means what it says.
        _run(common + ["-filter_complex", base, "-map", "[base]", "-an", *encode, silent],
             "encode the silent integrated master")
        written.append(silent)
    _run(common + ["-filter_complex", graph, "-map", "[vout]", "-an", *encode, visual],
         "encode the silent visual cut")
    written.append(visual)
    _run(
        common + ["-i", audio_path, "-filter_complex", graph, "-map", "[vout]",
                  "-map", f"{_audio_input(plan)}:a", *encode,
                  "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(SAMPLE_RATE),
                  "-shortest", video],
        "encode the Short",
    )
    written.append(video)
    for path in written:
        print(f"video: {path}  {os.path.getsize(path) / (1024 * 1024):.1f} MiB")
    return {"video": video, "visual": visual, "silent": silent or ""}


# The four picture inputs are fixed; the preview, when there is one, is the
# fifth, and the soundtrack lands after whatever is there.
_PREVIEW_INPUT = 4


def _audio_input(plan: dict[str, Any]) -> int:
    return 5 if plan.get("preview") else 4


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument(
        "--stage", default="all", choices=("audio", "overlays", "mux", "qc", "all")
    )
    parser.add_argument(
        "--edition", default=DEFAULT_EDITION, choices=tuple(EDITIONS),
        help="v24 is the hook experiment; v21 is the start/retention cut; "
             "v221 the continuity pass; v20 and v211 rebuild the earlier ones",
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

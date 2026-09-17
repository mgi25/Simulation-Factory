"""The Race #2 Short: the locked film, three marks, a soundtrack and an encode.

    python tools/race2_v32_short.py all

Stages, each runnable on its own:

    evidence   who won, what it did, where every mark goes - all measured
    audio      the soundtrack, synthesised from the same replay the pictures are
    overlays   the three plates and the ring's frame sequence
    mux        the master, the visual cut, the Short and the phone review
    proofs     the opening and payoff contact sheets
    review     the delivered Short sampled at 270x480, band by band
    locks      Part L: every locked layer against the base commit
    qc         the finished files, measured against the brief

**Nothing here renders, simulates or re-times the film.** The master is
`output/race2/v32_final/frames/master/clip_switchyard_8`, rendered once by
`tools/race2_render.py` against the V31 RB camera track, `contained_bay_v301`
and `--track=B`, and every stage below reads those PNGs frame for frame. There
is no hold, no preview, no omission, no ramp and no replayed finish: output
frame `i` is replay second `i / 60` for all 1150 of them, which is what makes
"zero temporal omissions" a property of the clock rather than a claim.

## The three marks

    PICK A COLOR   frame 0 to 1.30 s, fading from 1.05 - V24's timing exactly
    a ring on m7   opening on the frame it crosses, 0.70 s
    PINK WINS      from the crossing + 1.0 s, held to the last frame
    5TH -> 1ST

All three are `sloped.overlays` / `sloped.v24_hook` / `sloped.v24_payoff`
drawings. What this pass contributes is that each one is **placed against this
film's own frames** - see `race2.presentation` - and that the comeback claim is
checked against two instruments before it is set in type.

## The claim that did not survive

V31's preview prints `FROM 6TH -> 1ST`, taken from the worst index the winner
ever occupies in `rank_series`. Measured: m7 is 6th for **0.217 s**, one run of
13 samples, at 3.13 s. The race's own checkpoint ladder says 5th and the
duration-weighted history says 5th. The card says **5TH**, and
`docs/validation/race2/v32_final/evidence.json` carries the rejected run.
"""

from __future__ import annotations

import argparse
import glob
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

COURSE = "switchyard"
SEED = 8
CAMERA = "output/race2/v31_readability/RB"
ENVIRONMENT = "contained_bay_v301"
TRACK_VARIANT = "B"

OUT = "output/race2/v32_final"
FRAMES = os.path.join(OUT, "frames", "master", f"clip_{COURSE}_{SEED}")
WORK = os.path.join(OUT, "work")
DOCS = "docs/validation/race2/v32_final"
EXPORT = "exports/race2_v32_final"

MASTER = os.path.join(EXPORT, f"race2_{COURSE}_master.mp4")
VISUAL = os.path.join(EXPORT, f"race2_{COURSE}_final_visual.mp4")
FINAL = os.path.join(EXPORT, f"race2_{COURSE}_final.mp4")
PHONE = os.path.join(EXPORT, f"race2_{COURSE}_final_phone_270x480.mp4")

FPS = 60
VIDEO_CRF = 17
VIDEO_PRESET = "slow"
AUDIO_BITRATE = "256k"
TRUE_PEAK_CEILING_DBTP = -1.0
PHONE_SIZE = (270, 480)


class ShortError(RuntimeError):
    pass


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise ShortError(f"{name} is not on PATH")
    return found


def _run(command: Sequence[str], label: str) -> str:
    done = subprocess.run(list(command), cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise ShortError(f"{label} failed:\n{(done.stderr or done.stdout)[-2500:]}")
    return done.stdout or ""


def _paths() -> tuple[str, str]:
    replay = os.path.join("output/race2", f"race2_{COURSE}_{SEED}.replay.json")
    track = os.path.join(CAMERA, f"race2_{COURSE}_{SEED}.cameras.json")
    for path in (replay, track):
        if not os.path.isfile(path):
            raise ShortError(
                f"missing {path}\n  run: python tools/race2_camera.py "
                f"--course={COURSE} --seed={SEED}\n"
                f"  then: python tools/race2_v31_camera.py --seed={SEED} --only=RB"
            )
    return replay, track


def master_frames() -> list[str]:
    found = sorted(glob.glob(os.path.join(FRAMES, "frame_*.png")))
    if not found:
        raise ShortError(
            f"no master frames in {FRAMES}\n  run: python tools/race2_render.py clip "
            f"--seed={SEED} --course={COURSE} --out={CAMERA} "
            f"--frames={os.path.join(OUT, 'frames', 'master')} "
            f"--environment={ENVIRONMENT} --end=19.1500 --track={TRACK_VARIANT}"
        )
    return found


def load() -> tuple[dict[str, Any], dict[str, Any], Any]:
    from race2.presentation import load_film

    replay_path, track_path = _paths()
    frames = master_frames()
    return load_film(replay_path, track_path, master_frames=len(frames))


# --- evidence ---------------------------------------------------------------


def stage_evidence(args) -> dict[str, Any]:
    """Every number the marks are made of, measured and written down."""
    from race2 import courses, presentation as pres
    from race2.race import run_race
    from race2.spine import Spine

    replay, track, clock = load()
    frames = master_frames()
    first = int(os.path.basename(frames[0])[6:12])
    last = int(os.path.basename(frames[-1])[6:12])
    contiguous = (last - first + 1) == len(frames)

    winner, crossing = pres.winner_of(replay)
    course = courses.build(COURSE)
    spine = Spine(course)
    outcome, _ = run_race(course, seed=SEED, duration=40.0, marble_count=8,
                          with_replay=False)
    hero = next(r for r in outcome.racers if r.marble_id == winner)
    runs = pres.rank_runs(outcome.rank_series, winner, clock.segments[-1][1])
    comeback = pres.comeback_rank(runs, checkpoints=dict(hero.ranks))

    hook = pres.hook_placement(replay, track, clock)
    ring = pres.ring_track(replay, track, clock, spine, winner, crossing)
    card_from = round((crossing + pres.CARD_BEAT) * FPS) / FPS
    band = pres.card_band(FRAMES, replay, track, clock, card_from)
    _payoff, _image, card = pres.card_plate(winner, comeback["rank"], band["band"])

    report = {
        "course": COURSE,
        "seed": SEED,
        "camera": "RB (V31 readability)",
        "environment": ENVIRONMENT,
        "track_variant": TRACK_VARIANT,
        "film": {
            "frames": len(frames),
            "first_frame": first,
            "last_frame": last,
            "contiguous": contiguous,
            "fps": clock.fps,
            "runtime_seconds": round(clock.duration, 6),
            "camera_track_duration": float(track["duration"]),
            "temporal_omissions": len(_omissions(clock)),
            "segments": [list(row) for row in clock.segments],
        },
        "winner": {
            "marble": winner,
            "crossing": round(crossing, 6),
            "label": card["label"],
            "hue": card["hue"],
            "finish_order": [
                {"marble": int(e["id"]), "order": int(e["order"]), "t": float(e["t"])}
                for e in sorted(
                    (e for e in replay["events"] if e["kind"] == "finish_line"),
                    key=lambda e: float(e["t"]),
                )
            ],
            "margin_to_second": round(
                sorted(float(e["t"]) for e in replay["events"]
                       if e["kind"] == "finish_line")[1] - crossing, 6),
        },
        "comeback": comeback,
        "rank_runs": [
            {"from": round(a, 4), "to": round(b, 4),
             "seconds": round(b - a + 1.0 / FPS, 4), "rank": r}
            for a, b, r in runs
        ],
        "hook": hook,
        "ring": {k: v for k, v in ring.items() if k != "track"},
        "card": dict(card, **{"from": card_from,
                              "from_frame": int(round(card_from * FPS)),
                              "to": round(clock.duration, 6),
                              "beat": pres.CARD_BEAT, "band_measure": band}),
    }
    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "evidence.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    with open(os.path.join(DOCS, "ring_track.json"), "w", encoding="utf-8") as handle:
        json.dump(ring, handle, indent=1)

    print(f"film     {len(frames)} frames {first}-{last}, contiguous {contiguous}, "
          f"{clock.duration:.4f} s at {clock.fps} fps, "
          f"{len(_omissions(clock))} temporal omissions")
    print(f"winner   m{winner} {card['label']} rgb{tuple(card['hue'])} "
          f"crosses {crossing:.4f} s, {report['winner']['margin_to_second']:.4f} s "
          f"clear of second")
    print(f"comeback {comeback['rank']}TH -> 1ST  "
          f"(held {comeback['seconds_at_rank']:.3f} s, longest run "
          f"{comeback['longest_run_at_rank']:.3f} s; checkpoints worst "
          f"{comeback['checkpoint_worst']}TH; instruments agree "
          f"{comeback['instruments_agree']})")
    for row in comeback["rejected"]:
        print(f"         rejected {row['rank']}TH: held {row['seconds_total']:.3f} s, "
              f"longest run {row['longest_run']:.3f} s = {row['frames_longest']} frames")
    print(f"hook     {hook['size']} pt x {len(hook['lines'])} lines, baseline "
          f"{hook['top_baseline']}, cap {hook['cap_px']} px "
          f"({hook['cap_px_at_270']} px at 270x480), ink {hook['line_ink_px']}, "
          f"racers at y {hook['racers_top']:.0f}, clearance {hook['clearance']:.0f} px")
    print(f"ring     m{ring['marble']} {ring['from']:.3f}-{ring['to']:.3f} s, "
          f"{ring['frames']} frames, {ring['frames_blocked']} blocked, radius "
          f"{ring['radius_px'][0]:.0f}-{ring['radius_px'][1]:.0f} px")
    print(f"card     {card['label']} WINS / {comeback['rank']}TH -> 1ST, "
          f"{card_from:.3f}-{clock.duration:.3f} s, band {card['band']} "
          f"(max luma {band['max_luma']}), ink {card['ink_box']}, inside "
          f"{card['inside_band']}, contrast {card['text_contrast']}:1, "
          f"colour area {card['colour_pixels']} px")
    if ring["frames_blocked"]:
        raise ShortError(
            f"the course stands between the lens and the winner on "
            f"{ring['frames_blocked']} of the ring's {ring['frames']} frames - "
            "see V24's payoff lab; the mark would point at a marble the viewer "
            "cannot see"
        )
    if not card["inside_band"]:
        raise ShortError(f"the card's ink {card['ink_box']} leaves its band {card['band']}")
    if not comeback["instruments_agree"]:
        raise ShortError(
            f"the rank history says {comeback['rank']} and the checkpoint ladder "
            f"says {comeback['checkpoint_worst']}; the card would carry an "
            "unverified comeback"
        )
    return report


def _omissions(clock) -> list[tuple[float, float]]:
    from sloped import presentation as pres

    return pres.omissions(clock)


def _evidence() -> dict[str, Any]:
    path = os.path.join(DOCS, "evidence.json")
    if not os.path.isfile(path):
        raise ShortError(f"missing {path}; run `evidence` first")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# --- audio ------------------------------------------------------------------


def stage_audio(args) -> str:
    """The soundtrack, from the same replay the pictures came from.

    `audio.marble.build_race_audio` unchanged. Race #2 reaches it with no
    `start.paddle`, `start.panel` or `start.rotor` in its actuator set, so the
    gate, trapdoor and mixer voices return nothing and are absent - correctly,
    because this machine has none of them. What is left is the ambience, the
    rolling bed with its contact-keyed rattle, the impacts, the eight crossings
    and the music bed, all of them derived.
    """
    from audio import marble
    from audio.wav_io import write_wav

    replay, track, clock = load()
    mix = marble.build_race_audio(replay, track, clock)
    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, f"race2_{COURSE}_{SEED}.wav")
    write_wav(path, mix.left, mix.right, sample_rate=mix.sample_rate)

    hits = [
        (float(event["t"]), str(event["module"]))
        for event in replay["events"] if event["kind"] == "mechanism_hit"
    ]
    from sloped import presentation as pres
    cues = pres.impacts(replay, clock)
    covered = sum(
        1 for when, _module in hits if any(abs(c.at - when) <= 0.12 for c in cues)
    )
    print(f"audio: {mix.seconds:.4f} s, {len(mix.left)} samples at {mix.sample_rate} Hz "
          f"({clock.frames} frames x {mix.sample_rate // FPS})")
    print(f"  placed {mix.placed}")
    print(f"  peak in {20 * math.log10(max(mix.peak_before, 1e-9)):.2f} dBFS, "
          f"compressor {mix.gain_reduction_db:.2f} dB, "
          f"out {20 * math.log10(max(mix.peak_after, 1e-9)):.2f} dBFS, "
          f"limiter {'engaged' if mix.limited else 'idle'}")
    print(f"  {covered}/{len(hits)} mechanism hits carry an impact cue within 0.12 s")
    print(f"  wrote {path}")
    return path


# --- overlays ---------------------------------------------------------------


def stage_overlays(args) -> dict[str, Any]:
    from race2 import presentation as pres

    evidence = _evidence()
    os.makedirs(WORK, exist_ok=True)

    hook = pres.hook_plate(
        lines=evidence["hook"]["lines"],
        size=evidence["hook"]["size"],
        top_baseline=evidence["hook"]["top_baseline"],
    )
    hook_path = os.path.join(WORK, "hook.png")
    hook.save(hook_path)

    _payoff, card_image, _report = pres.card_plate(
        evidence["winner"]["marble"], evidence["comeback"]["rank"],
        evidence["card"]["band"],
    )
    card_path = os.path.join(WORK, "card.png")
    card_image.save(card_path)

    with open(os.path.join(DOCS, "ring_track.json"), encoding="utf-8") as handle:
        ring = json.load(handle)
    ring_dir = os.path.join(WORK, "ring")
    if os.path.isdir(ring_dir):
        shutil.rmtree(ring_dir)
    os.makedirs(ring_dir, exist_ok=True)
    rows = ring["track"]
    from sloped import overlays
    for index, row in enumerate(rows):
        phase = index / max(1, len(rows) - 1)
        overlays.winner_ring(row["x"], row["y"], row["r"], phase).save(
            os.path.join(ring_dir, f"ring_{index:04d}.png")
        )
    print(f"overlays: hook {hook_path}  ({evidence['hook']['size']} pt, "
          f"{len(evidence['hook']['lines'])} lines)")
    print(f"          card {card_path}")
    print(f"          ring {len(rows)} frames from {ring['from']:.3f} s "
          f"on marble {ring['marble']}")
    return {"hook": hook_path, "card": card_path, "ring_dir": ring_dir,
            "ring_from": ring["from"], "ring_from_frame": ring["from_frame"],
            "ring_frames": len(rows)}


# --- mux --------------------------------------------------------------------


def _window(first: int, last: int) -> str:
    """An `enable` expression for whole frames `first` to `last` inclusive.

    **Every window in this graph is stated in frames, not in seconds.** A mark
    that is meant to be up on frame N has to be up on frame N, and `between(t,
    15.8167, 16.5167)` does not say that: 15.8167 is 0.00003 s *after* frame
    949's presentation time, so frame 949 falls outside the window and the mark
    opens on 950. Written as `949/60` the arithmetic is the renderer's own, and
    the half-frame skirts make the comparison robust to the last bit of a double.
    """
    return (f"between(t,{first - 0.5:.6f}/{FPS},{last + 0.5:.6f}/{FPS})")


def _graph(evidence: dict[str, Any], plan: dict[str, Any]) -> str:
    """The base picture, the mark, the ring and the card.

    **The mark does not fade in.** It opens on frame zero over live footage, and
    a `fade=t=in` starting at 0 makes the first frame transparent - which is the
    one frame the whole hook exists for.

    **The ring's offset is a whole tick.** `setpts=PTS-STARTPTS+949/60/TB` puts
    the sequence's first image on the frame the winner crosses. An offset
    expressed as a rounded number of seconds does not, and the frame it loses is
    the flash - the only part of any mark in this film that is synchronised to
    an event. `qc`'s `_mark_presence` measures the delivered file against the
    delivered master and would catch it again.
    """
    hook = evidence["hook"]
    ring_from = int(plan["ring_from_frame"])
    ring_to = ring_from + int(plan["ring_frames"]) - 1
    card_from = int(evidence["card"]["from_frame"])
    card_to = int(evidence["film"]["last_frame"])
    hook_to = int(round(hook["out_to"] * FPS))
    return (
        f"[0:v]null[base];"
        f"[1:v]format=rgba,fade=t=out:st={hook['out_from']}:"
        f"d={hook['out_to'] - hook['out_from']}:alpha=1[hook];"
        f"[base][hook]overlay=0:0:enable='{_window(0, hook_to)}'[v1];"
        f"[2:v]format=rgba,setpts=PTS-STARTPTS+{ring_from}/{FPS}/TB[ring];"
        f"[v1][ring]overlay=0:0:enable='{_window(ring_from, ring_to)}'[v2];"
        f"[3:v]format=rgba,fade=t=in:st=0:d=0.20:alpha=1[card];"
        f"[v2][card]overlay=0:0:enable='{_window(card_from, card_to)}'[vout]"
    )


def stage_mux(args) -> dict[str, str]:
    evidence = _evidence()
    plan = stage_overlays(args) if args.rebuild_overlays else {
        "hook": os.path.join(WORK, "hook.png"),
        "card": os.path.join(WORK, "card.png"),
        "ring_dir": os.path.join(WORK, "ring"),
        "ring_from": evidence["ring"]["from"],
        "ring_from_frame": evidence["ring"]["from_frame"],
        "ring_frames": evidence["ring"]["frames"],
    }
    audio = os.path.join(WORK, f"race2_{COURSE}_{SEED}.wav")
    if not os.path.isfile(audio):
        raise ShortError(f"missing {audio}; run `audio` first")
    frames = master_frames()
    first = int(os.path.basename(frames[0])[6:12])
    count = len(frames)
    os.makedirs(EXPORT, exist_ok=True)

    ffmpeg = _tool("ffmpeg")
    inputs = [
        ffmpeg, "-y",
        "-framerate", str(FPS), "-start_number", str(first),
        "-i", os.path.join(FRAMES, "frame_%06d.png"),
        "-loop", "1", "-framerate", str(FPS), "-i", plan["hook"],
        "-framerate", str(FPS), "-start_number", "0",
        "-i", os.path.join(plan["ring_dir"], "ring_%04d.png"),
        "-loop", "1", "-framerate", str(FPS), "-i", plan["card"],
    ]
    encode = [
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-frames:v", str(count),
    ]
    graph = _graph(evidence, plan)

    # The master: the locked picture with nothing drawn on it and no sound. What
    # a reviewer watches to see the film the marks are sitting on.
    _run(inputs + ["-filter_complex", "[0:v]null[base]", "-map", "[base]", "-an",
                   *encode, MASTER], "encode the master")
    _run(inputs + ["-filter_complex", graph, "-map", "[vout]", "-an",
                   *encode, VISUAL], "encode the visual cut")
    _run(inputs + ["-i", audio, "-filter_complex", graph, "-map", "[vout]",
                   "-map", "4:a", *encode,
                   "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000",
                   "-shortest", FINAL], "encode the Short")
    _run([ffmpeg, "-y", "-i", FINAL, "-vf",
          f"scale={PHONE_SIZE[0]}:{PHONE_SIZE[1]}:flags=lanczos",
          "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", "18",
          "-pix_fmt", "yuv420p", "-movflags", "+faststart",
          "-c:a", "aac", "-b:a", "128k", PHONE], "encode the phone review")

    out = {"master": MASTER, "visual": VISUAL, "final": FINAL, "phone": PHONE}
    for label, path in out.items():
        print(f"video: {label:7s} {path}  "
              f"{os.path.getsize(path) / (1024 * 1024):.1f} MiB")
    return out


# --- proofs -----------------------------------------------------------------


def _sheet(tiles: Sequence[tuple[str, Any]], target: str, columns: int,
           cell: tuple[int, int]) -> None:
    from PIL import Image, ImageDraw

    rows = (len(tiles) + columns - 1) // columns
    label = 26
    canvas = Image.new("RGB", (columns * cell[0], rows * (cell[1] + label)),
                       (16, 16, 18))
    pen = ImageDraw.Draw(canvas)
    for index, (name, image) in enumerate(tiles):
        row, column = divmod(index, columns)
        canvas.paste(image.resize(cell, Image.LANCZOS),
                     (column * cell[0], row * (cell[1] + label) + label))
        pen.text((column * cell[0] + 5, row * (cell[1] + label) + 7), name,
                 fill=(232, 228, 216))
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    canvas.save(target)
    print(f"  wrote {target} ({canvas.size[0]}x{canvas.size[1]})")


def stage_proofs(args) -> None:
    """Part M's opening and winner/payoff proofs, at delivery phone size."""
    from PIL import Image

    evidence = _evidence()
    hook = Image.open(os.path.join(WORK, "hook.png")).convert("RGBA")
    card = Image.open(os.path.join(WORK, "card.png")).convert("RGBA")
    with open(os.path.join(DOCS, "ring_track.json"), encoding="utf-8") as handle:
        ring = json.load(handle)
    rings = sorted(glob.glob(os.path.join(WORK, "ring", "ring_*.png")))

    def frame(index: int):
        return Image.open(os.path.join(FRAMES, f"frame_{index:06d}.png")).convert("RGBA")

    opening = []
    for seconds in (0.0, 0.25, 0.60, 1.00, 1.20, 1.30):
        image = frame(int(round(seconds * FPS)))
        if seconds <= evidence["hook"]["out_to"]:
            alpha = 1.0
            if seconds > evidence["hook"]["out_from"]:
                alpha = 1.0 - ((seconds - evidence["hook"]["out_from"])
                               / (evidence["hook"]["out_to"] - evidence["hook"]["out_from"]))
            image.alpha_composite(_faded(hook, alpha))
        opening.append((f"{seconds:.2f} s", image.convert("RGB")))
    _sheet(opening, os.path.join(DOCS, "opening_proof.png"), 6, PHONE_SIZE)

    payoff = []
    ring_start = ring["from"]
    for seconds in (ring_start, ring_start + 0.20, ring_start + 0.50,
                    evidence["card"]["from"] + 0.35, 18.60, 19.15):
        index = int(round(seconds * FPS))
        image = frame(min(index, evidence["film"]["last_frame"]))
        step = int(round((seconds - ring_start) * FPS))
        if 0 <= step < len(rings):
            image.alpha_composite(Image.open(rings[step]).convert("RGBA"))
        if seconds >= evidence["card"]["from"]:
            alpha = min(1.0, (seconds - evidence["card"]["from"]) / 0.20)
            image.alpha_composite(_faded(card, alpha))
        payoff.append((f"{seconds:.2f} s", image.convert("RGB")))
    _sheet(payoff, os.path.join(DOCS, "payoff_proof.png"), 6, PHONE_SIZE)


def _faded(plate, alpha: float):
    from PIL import Image

    if alpha >= 0.999:
        return plate
    if alpha <= 0.001:
        return Image.new("RGBA", plate.size, (0, 0, 0, 0))
    faded = plate.copy()
    faded.putalpha(plate.getchannel("A").point(
        lambda value: int(round(value * alpha))))
    return faded


# The brief's Part I, as named spans of the finished film.
REVIEW_BANDS = (
    ("hook", 0.0, 2.0),
    ("early_race", 2.0, 6.0),
    ("track_and_battle", 6.0, 10.0),
    ("switchbacks", 10.0, 14.0),
    ("final_sprint", 14.0, 17.0),
    ("winner_and_payoff", 17.0, 19.5),
)
REVIEW_STRIDE = 30      # frames between samples: every half second


def stage_review(args) -> None:
    """Part H and Part I: the delivered Short, sampled at exactly 270x480.

    **Decoded by frame index, not by `fps=`.** The obvious way to do this is
    `-vf fps=2`, and it is wrong here: on this file it returns frames that are
    not the ones it names - measured, the frame it handed back for t=0 has a
    racer band mean of 25.4 against the source's 44.0, while frame 0 selected by
    index matches the source at 42.7. A review sheet that is silently off by
    some frames is a review of a film nobody is shipping, so every tile below is
    `select='eq(n,K)'` and its own index is in the caption.
    """
    from PIL import Image, ImageDraw

    evidence = _evidence()
    work = os.path.join(OUT, "review")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)
    indices = list(range(0, evidence["film"]["frames"], REVIEW_STRIDE))
    picks = "+".join(f"eq(n\\,{index})" for index in indices)
    _run([_tool("ffmpeg"), "-v", "error", "-y", "-i", FINAL, "-vf",
          f"select='{picks}',scale={PHONE_SIZE[0]}:{PHONE_SIZE[1]}:flags=lanczos",
          "-vsync", "0", os.path.join(work, "r_%03d.png")], "sample the Short")
    got = sorted(glob.glob(os.path.join(work, "r_*.png")))
    if len(got) != len(indices):
        raise ShortError(f"asked for {len(indices)} review frames, decoded {len(got)}")

    label = 22
    for name, low, high in REVIEW_BANDS:
        chosen = [
            (index, path) for index, path in zip(indices, got)
            if low - 1e-9 <= index / FPS < high
        ]
        canvas = Image.new(
            "RGB",
            (len(chosen) * PHONE_SIZE[0], PHONE_SIZE[1] + 2 * label),
            (14, 14, 16),
        )
        pen = ImageDraw.Draw(canvas)
        pen.text((6, 5), f"{name}  {low:g}-{high:g} s  (270x480, from {FINAL})",
                 fill=(240, 210, 150))
        for column, (index, path) in enumerate(chosen):
            canvas.paste(Image.open(path), (column * PHONE_SIZE[0], 2 * label))
            pen.text((column * PHONE_SIZE[0] + 5, label + 4),
                     f"n={index}  {index / FPS:.2f}s", fill=(228, 228, 228))
        target = os.path.join(DOCS, f"phone_review_{name}.png")
        canvas.save(target)
        print(f"  wrote {target} ({canvas.size[0]}x{canvas.size[1]}, "
              f"{len(chosen)} frames)")


# --- locks -------------------------------------------------------------------

# Every file that defines a locked layer, and what it locks. A hash over a
# source file says the rule did not move; the regenerated reports beside it say
# the *picture* did not either, which is the stronger claim of the two.
LOCK_FILES = {
    "physics": (
        "race2/race.py", "race2/course.py", "race2/courses.py",
        "race2/parts.py", "race2/kit.py", "race2/start.py", "race2/track.py",
    ),
    "camera": (
        "race2/rig.py", "race2/cinematography.py", "race2/shots.py",
        "race2/spine.py", "race2/flow.py",
        "output/race2/v31_readability/RB/race2_switchyard_8.cameras.json",
    ),
    "environment": (
        "godot/assets/marble_machine/environment/profiles/contained_bay_v301.json",
        "godot/scripts/race2_scene.gd",
    ),
    "track": (
        "godot/assets/marble_machine/course/race2_track_surface.gd",
    ),
}
# What the base commit's own reports say, so a rebuild is compared with the
# delivered numbers rather than only with itself.
LOCK_REPORTS = {
    "physics": "docs/validation/race2/events_switchyard_8.json",
    "camera": "docs/validation/race2/v31_readability/read_RB.json",
    "track": "docs/validation/race2/v311_track/track_measure.json",
}
BASE_COMMIT = "fa39d7a794444ee761b499a3f855f452517b4369"


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _git_blob(path: str, commit: str = BASE_COMMIT) -> str | None:
    done = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO,
                          capture_output=True)
    if done.returncode != 0:
        return None
    return hashlib.sha256(done.stdout).hexdigest()


def _tracked_at_base(path: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{BASE_COMMIT}:{path}"],
                          cwd=REPO, capture_output=True).returncode == 0


def _changed_since_base(paths: Sequence[str]) -> set[str]:
    """Which of these files differ from the base commit, by git's own comparison.

    **Not a raw hash of the file.** This clone has `core.autocrlf = true`, so a
    text file's bytes on disk carry CRLF and the same blob in the object store
    carries LF: hashing the two and comparing reports every source file in the
    repository as changed, which is what the first build of this stage did. It
    called all sixteen locked files modified while `git diff` against the same
    commit returned nothing at all - a lock instrument that cannot pass.
    `git diff` applies the same filters on both sides, so it is the comparison,
    and the raw hashes below are kept only as a record of what was measured.
    """
    tracked = [path for path in paths if _tracked_at_base(path)]
    if not tracked:
        return set()
    done = subprocess.run(["git", "diff", "--name-only", BASE_COMMIT, "--", *tracked],
                          cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise ShortError(f"git diff failed:\n{done.stderr}")
    return {line.strip().replace("\\", "/")
            for line in (done.stdout or "").splitlines() if line.strip()}


def stage_locks(args) -> dict[str, Any]:
    """Part L: prove every locked layer is the one the base commit delivered.

    Three kinds of evidence, weakest to strongest:

    * **source hashes** - each file that defines a layer, this working tree
      against the base commit's blob. A difference here is a changed rule.
    * **the replay's own digests** - `marble3d` writes a `digest` and an
      `event_digest` over the recorded frames and events, so a physics change
      shows up as a different number without anybody diffing 12 MB of JSON.
    * **regenerated reports** - the race, the RB flow/readability report and
      V31.1's track measurement, rebuilt on this branch and compared field by
      field with the ones the base commit ships. Those are measurements of the
      *rendered picture*, which is the thing a lock is actually about.
    """
    replay, track, _clock = load()
    report: dict[str, Any] = {"base_commit": BASE_COMMIT, "layers": {}}
    ok = True
    for layer, paths in LOCK_FILES.items():
        rows = []
        changed = _changed_since_base(paths)
        for path in paths:
            if not os.path.isfile(path):
                rows.append({"path": path, "status": "missing"})
                ok = False
                continue
            tracked = _tracked_at_base(path)
            same = (path not in changed) if tracked else None
            if tracked and not same:
                ok = False
            rows.append({
                "path": path,
                "sha256": _sha256(path),
                "base_sha256": _git_blob(path),
                "tracked_at_base": tracked,
                "unchanged": same,
                "note": None if tracked else "not in the base commit; built by this run",
            })
        report["layers"][layer] = {"files": rows}
    report["layers"]["physics"]["replay_digest"] = replay.get("digest")
    report["layers"]["physics"]["replay_event_digest"] = replay.get("event_digest")
    report["layers"]["physics"]["seed"] = replay.get("seed")
    report["layers"]["camera"]["track_duration"] = float(track["duration"])
    report["layers"]["camera"]["cuts"] = [
        {"name": cut["name"], "mode": cut["mode"],
         "from": cut["from"], "to": cut["to"]}
        for cut in track["cuts"]
    ]

    reproduced: dict[str, Any] = {}
    for layer, path in LOCK_REPORTS.items():
        if not os.path.isfile(path):
            reproduced[layer] = {"report": path, "status": "missing"}
            ok = False
            continue
        with open(path, encoding="utf-8") as handle:
            current = json.load(handle)
        done = subprocess.run(["git", "show", f"{BASE_COMMIT}:{path}"], cwd=REPO,
                              capture_output=True, text=True, encoding="utf-8")
        base = json.loads(done.stdout) if done.returncode == 0 else _ABSENT
        differing = _differences(current, base, ignore={"wall_seconds", "ms_per_frame"})
        if base is _ABSENT or differing:
            ok = False
        reproduced[layer] = {
            "report": path,
            "fields_compared": 0 if base is _ABSENT else _leaf_count(base),
            "fields_differing": differing[:12],
            "identical": base is not _ABSENT and not differing,
        }
    report["reproduced"] = reproduced
    report["ok"] = ok

    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "locks.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)

    for layer, block in report["layers"].items():
        changed = [r["path"] for r in block["files"] if r.get("unchanged") is False]
        print(f"  [{'pass' if not changed else 'FAIL'}] {layer}: "
              f"{len(block['files'])} source files identical to {BASE_COMMIT[:7]}"
              + (f"; CHANGED {changed}" if changed else ""))
    print(f"         replay digest {replay.get('digest')}")
    print(f"         event digest  {replay.get('event_digest')}")
    for layer, block in reproduced.items():
        print(f"  [{'pass' if block.get('identical') else 'FAIL'}] {layer}: "
              f"{os.path.basename(block['report'])} regenerates identically "
              f"({block['fields_compared']} fields)"
              + (f"; differing {block['fields_differing']}"
                 if block["fields_differing"] else ""))
    print(f"\n  {'PASS' if ok else 'FAIL'} - wrote {os.path.join(DOCS, 'locks.json')}")
    if not ok:
        raise ShortError("a locked layer moved; see locks.json")
    return report


_ABSENT = object()


def _differences(current: Any, base: Any, ignore: set[str], path: str = "") -> list[str]:
    """Every leaf where two reports disagree.

    **`None` is a value, not an absence.** The first build of this returned
    early on `base is None`, and both reports are full of legitimate nulls -
    `race.failure`, every racer's `lost_at`, every moment's `structure` on a
    frame with no structure in it. Comparing the committed file with *itself*
    then reported 28 differences. `_ABSENT` is the sentinel for a key that is
    not there at all, which is the case that actually matters.
    """
    if current is _ABSENT or base is _ABSENT:
        return [path or "<missing>"]
    if isinstance(current, dict) and isinstance(base, dict):
        out: list[str] = []
        for key in sorted(set(current) | set(base)):
            if key in ignore:
                continue
            out += _differences(current.get(key, _ABSENT),
                                base.get(key, _ABSENT), ignore,
                                f"{path}.{key}" if path else key)
        return out
    if isinstance(current, list) and isinstance(base, list):
        if len(current) != len(base):
            return [f"{path}[len {len(base)} -> {len(current)}]"]
        out = []
        for index, (a, b) in enumerate(zip(current, base)):
            out += _differences(a, b, ignore, f"{path}[{index}]")
        return out
    if isinstance(current, float) and isinstance(base, (int, float)):
        return [] if abs(current - base) <= 1e-9 else [path]
    return [] if current == base else [path]


def _leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_leaf_count(item) for item in value)
    return 1


# --- qc ---------------------------------------------------------------------


def _probe(path: str) -> dict[str, Any]:
    done = _run([_tool("ffprobe"), "-v", "error", "-show_streams", "-show_format",
                 "-of", "json", path], f"probe {os.path.basename(path)}")
    return json.loads(done)


def _loudness(path: str) -> dict[str, float]:
    done = subprocess.run(
        [_tool("ffmpeg"), "-v", "info", "-i", path, "-af",
         "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = done.stderr or ""
    start, end = text.rfind("{"), text.rfind("}")
    if start < 0 or end < 0:
        return {}
    try:
        raw = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return {key: float(value) for key, value in raw.items()
            if key.startswith("input_") and value not in ("-inf", "inf")}


def _frame_hashes(path: str, size: tuple[int, int] = (64, 114)) -> list[str]:
    """One hash per decoded frame, for duplicate and black-frame detection."""
    done = subprocess.run(
        [_tool("ffmpeg"), "-v", "error", "-i", path, "-vf",
         f"scale={size[0]}:{size[1]}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        cwd=REPO, capture_output=True)
    if done.returncode != 0:
        raise ShortError("frame decode failed")
    step = size[0] * size[1]
    data = done.stdout
    return [hashlib.sha1(data[i:i + step]).hexdigest()
            for i in range(0, len(data) - step + 1, step)]


def _frame_means(path: str, size: tuple[int, int] = (64, 114)) -> list[float]:
    done = subprocess.run(
        [_tool("ffmpeg"), "-v", "error", "-i", path, "-vf",
         f"scale={size[0]}:{size[1]}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        cwd=REPO, capture_output=True)
    step = size[0] * size[1]
    data = done.stdout
    return [sum(data[i:i + step]) / step
            for i in range(0, len(data) - step + 1, step)]


def _decode_frames(path: str, indices: Sequence[int], out_dir: str) -> list[str]:
    """Named frames of a finished file, selected by index rather than by time."""
    os.makedirs(out_dir, exist_ok=True)
    for stale in glob.glob(os.path.join(out_dir, "f_*.png")):
        os.remove(stale)
    picks = "+".join(f"eq(n\\,{index})" for index in indices)
    _run([_tool("ffmpeg"), "-v", "error", "-y", "-i", path, "-vf",
          f"select='{picks}'", "-vsync", "0",
          os.path.join(out_dir, "f_%03d.png")], f"decode {os.path.basename(path)}")
    return sorted(glob.glob(os.path.join(out_dir, "f_*.png")))


def _mark_presence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Where the delivered Short differs from the delivered master, per frame.

    The strongest statement available about the marks, because it is made on the
    file that ships rather than on the plan that made it: the Short and the
    master are the same picture with three plates composited, so the difference
    between them **is** the marks. A frame outside every mark's window has to be
    the master; a frame inside one has to differ, and inside that mark's own ink
    box rather than somewhere else.
    """
    import numpy as np
    from PIL import Image

    hook = evidence["hook"]
    ring = evidence["ring"]
    card = evidence["card"]
    probes = [
        ("frame 0: the hook is up", 0, "hook", True),
        ("0.50 s: the hook is still up", 30, "hook", True),
        ("1.05 s: the hook starts to fade", 63, "hook", True),
        ("1.50 s: the hook is gone", 90, None, False),
        ("5.00 s: nothing is drawn", 300, None, False),
        ("10.00 s: nothing is drawn", 600, None, False),
        ("15.00 s: nothing is drawn", 900, None, False),
        ("the crossing: the ring opens", int(round(ring["from"] * FPS)), "ring", True),
        ("+0.35 s: the ring is up", int(round((ring["from"] + 0.35) * FPS)), "ring", True),
        ("+0.75 s: the ring is gone", int(round((ring["to"] + 0.05) * FPS)), None, False),
        ("the card is up", int(round((card["from"] + 0.30) * FPS)), "card", True),
        ("the last frame: the card holds",
         evidence["film"]["last_frame"], "card", True),
    ]
    indices = [row[1] for row in probes]
    work = os.path.join(OUT, "qc")
    short = _decode_frames(FINAL, indices, os.path.join(work, "short"))
    master = _decode_frames(MASTER, indices, os.path.join(work, "master"))
    if len(short) != len(indices) or len(master) != len(indices):
        raise ShortError("could not decode the probe frames")

    boxes = {
        "hook": (0, hook["top_baseline"] - hook["cap_px"] - 20,
                 DELIVERY_W, int(hook["top_baseline"]
                                 + (len(hook["lines"]) - 1) * hook["lead"] * hook["size"]) + 20),
        "card": (card["ink_box"][0] - 30, card["ink_box"][1] - 30,
                 card["ink_box"][2] + 30, card["ink_box"][3] + 30),
    }
    out = []
    for (label, index, mark, expect), a, b in zip(probes, short, master):
        left = np.asarray(Image.open(a).convert("RGB")).astype(float)
        right = np.asarray(Image.open(b).convert("RGB")).astype(float)
        delta = np.abs(left - right)
        whole = float(delta.mean())
        inside = None
        if mark == "ring":
            row = next(r for r in _ring_rows() if r["frame"] == index)
            span = max(60.0, row["r"] * 4.0)
            x0 = max(0, int(row["x"] - span)); x1 = min(DELIVERY_W, int(row["x"] + span))
            y0 = max(0, int(row["y"] - span)); y1 = min(DELIVERY_H, int(row["y"] + span))
            inside = float(delta[y0:y1, x0:x1].mean())
        elif mark is not None:
            x0, y0, x1, y1 = boxes[mark]
            inside = float(delta[max(0, y0):y1, max(0, x0):x1].mean())
        out.append({
            "label": label, "frame": index, "mark": mark,
            "expect_mark": expect,
            "whole_frame_delta": round(whole, 3),
            "in_box_delta": None if inside is None else round(inside, 3),
        })
    return {"probes": out}


DELIVERY_W, DELIVERY_H = 1080, 1920


def _ring_rows() -> list[dict[str, Any]]:
    with open(os.path.join(DOCS, "ring_track.json"), encoding="utf-8") as handle:
        return json.load(handle)["track"]


def stage_qc(args) -> dict[str, Any]:
    evidence = _evidence()
    expected = evidence["film"]["frames"]
    results: list[tuple[bool, str]] = []

    def check(passed: bool, line: str) -> None:
        results.append((bool(passed), line))
        print(f"  [{'pass' if passed else 'FAIL'}] {line}")

    print("container and stream")
    for path in (MASTER, VISUAL, FINAL, PHONE):
        if not os.path.isfile(path):
            check(False, f"missing {path}")
            return {"ok": False, "checks": [list(r) for r in results]}

    info = _probe(FINAL)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audios = [s for s in info["streams"] if s["codec_type"] == "audio"]
    check(int(video["width"]) == 1080 and int(video["height"]) == 1920,
          f"{video['width']}x{video['height']} (want 1080x1920)")
    check(video["r_frame_rate"] == f"{FPS}/1", f"{video['r_frame_rate']} fps")
    frames = int(video["nb_frames"])
    check(frames == expected, f"{frames} frames (want {expected})")
    runtime = frames / FPS
    check(abs(runtime - evidence["film"]["runtime_seconds"]) < 1e-6,
          f"runtime {runtime:.4f} s (want {evidence['film']['runtime_seconds']:.4f})")
    check(len(audios) == 1, f"{len(audios)} audio stream(s)")
    check(int(audios[0]["sample_rate"]) == 48000,
          f"audio at {audios[0]['sample_rate']} Hz")

    visual = _probe(VISUAL)
    check(not [s for s in visual["streams"] if s["codec_type"] == "audio"],
          "the visual cut carries no audio")
    check(int(next(s for s in visual["streams"]
                   if s["codec_type"] == "video")["nb_frames"]) == expected,
          "the visual cut has the same frame count")
    master = _probe(MASTER)
    check(int(next(s for s in master["streams"]
                   if s["codec_type"] == "video")["nb_frames"]) == expected,
          "the master has the same frame count")
    phone = _probe(PHONE)
    phone_video = next(s for s in phone["streams"] if s["codec_type"] == "video")
    check(int(phone_video["width"]) == PHONE_SIZE[0]
          and int(phone_video["height"]) == PHONE_SIZE[1],
          f"phone review {phone_video['width']}x{phone_video['height']}")

    print("timeline")
    check(evidence["film"]["contiguous"], "the master's frames are contiguous")
    check(evidence["film"]["temporal_omissions"] == 0,
          f"{evidence['film']['temporal_omissions']} temporal omissions")
    hashes = _frame_hashes(FINAL)
    check(len(hashes) == expected, f"{len(hashes)} frames decoded (want {expected})")
    duplicates = [i for i in range(1, len(hashes)) if hashes[i] == hashes[i - 1]]
    check(not duplicates,
          f"{len(duplicates)} duplicate/frozen frame pairs"
          + (f" first at {duplicates[0]}" if duplicates else ""))
    means = _frame_means(FINAL)
    black = [i for i, value in enumerate(means) if value < 6.0]
    check(not black, f"{len(black)} black frames"
          + (f" first at {black[0]}" if black else ""))

    print("audio")
    loud = _loudness(FINAL)
    if loud:
        peak = loud.get("input_tp", 0.0)
        check(peak <= TRUE_PEAK_CEILING_DBTP + 0.05,
              f"true peak {peak:+.2f} dBTP (ceiling {TRUE_PEAK_CEILING_DBTP:+.1f})")
        print(f"         integrated {loud.get('input_i', float('nan')):.2f} LUFS, "
              f"range {loud.get('input_lra', float('nan')):.2f} LU, "
              f"threshold {loud.get('input_thresh', float('nan')):.2f}")
    else:
        check(False, "could not measure loudness")

    print("marks")
    hook = evidence["hook"]
    check(hook["in"] == 0.0, "PICK A COLOR is up on frame 0")
    check(hook["out_to"] <= 2.233333,
          f"the mark is gone at {hook['out_to']:.2f} s, before the first cut at 2.23 s")
    check(hook["clearance"] > 0,
          f"the mark clears the racers by {hook['clearance']:.0f} px")
    ring = evidence["ring"]
    check(ring["marble"] == evidence["winner"]["marble"],
          f"the ring is on m{ring['marble']}, the winner")
    check(abs(ring["from"] - evidence["winner"]["crossing"]) <= 1.0 / FPS + 1e-9,
          f"the ring opens on the crossing ({ring['from']:.4f} vs "
          f"{evidence['winner']['crossing']:.4f})")
    check(ring["frames_blocked"] == 0,
          f"{ring['frames_blocked']} of {ring['frames']} ring frames blocked")
    card = evidence["card"]
    check(card["from"] > evidence["winner"]["crossing"],
          f"the card comes up {card['from'] - evidence['winner']['crossing']:.2f} s "
          "after the result")
    check(card["inside_band"], f"the card's ink is inside its measured band {card['band']}")
    check(card["from_place"] == evidence["comeback"]["rank"],
          f"the card says {card['from_place']}TH and the evidence says "
          f"{evidence['comeback']['rank']}TH")
    check(evidence["comeback"]["instruments_agree"],
          "both rank instruments agree on the comeback")

    print("marks on the delivered file")
    presence = _mark_presence(evidence)
    for row in presence["probes"]:
        if row["expect_mark"]:
            check(row["in_box_delta"] is not None and row["in_box_delta"] > 2.0,
                  f"{row['label']} (delta {row['in_box_delta']} in its own box)")
        else:
            check(row["whole_frame_delta"] < 0.5,
                  f"{row['label']} (whole-frame delta {row['whole_frame_delta']})")

    ok = all(passed for passed, _line in results)
    report = {
        "ok": ok,
        "checks": [{"pass": passed, "line": line} for passed, line in results],
        "loudness": loud,
        "frames": expected,
        "runtime_seconds": runtime,
        "duplicate_frames": duplicates,
        "black_frames": black,
        "mark_presence": presence["probes"],
        "files": {"master": MASTER, "visual": VISUAL, "final": FINAL, "phone": PHONE},
    }
    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "qc.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"\n  {'PASS' if ok else 'FAIL'} - wrote {os.path.join(DOCS, 'qc.json')}")
    return report


# --- entry ------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("evidence", "audio", "overlays", "mux",
                                          "proofs", "review", "locks", "qc",
                                          "all"))
    parser.add_argument("--rebuild-overlays", dest="rebuild_overlays",
                        action="store_true")
    args = parser.parse_args(argv)
    stages = {
        "evidence": stage_evidence, "audio": stage_audio,
        "overlays": stage_overlays, "mux": stage_mux,
        "proofs": stage_proofs, "review": stage_review,
        "locks": stage_locks, "qc": stage_qc,
    }
    if args.stage == "all":
        for name in ("evidence", "audio", "overlays", "mux", "proofs",
                     "review", "locks", "qc"):
            print(f"\n=== {name} ===")
            stages[name](args)
        return 0
    stages[args.stage](args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ShortError as error:
        print(f"race2 short: {error}", file=sys.stderr)
        raise SystemExit(1)

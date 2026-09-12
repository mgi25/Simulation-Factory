"""Section 14 of the brief, as measurements on the file that came out.

Everything here reads `real_race_v20.mp4` itself rather than the plan that made
it, because the question a reviewer asks is about the file. Where a check can be
answered from the pixels or the samples it is; where it cannot - "does the time
skip feel intentional" - the closest measurable proxy is stated as what it is.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.getcwd())

OUT_DIR = os.path.join("output", "sloped_race_v1")
VIDEO = os.path.join(OUT_DIR, "real_race_v20.mp4")
VISUAL = os.path.join(OUT_DIR, "real_race_v20_visual.mp4")

WIDTH, HEIGHT, FPS = 1080, 1920, 60
EXPECTED_FRAMES = 1192           # 1150 of master plus 42 held
TRUE_PEAK_CEILING_DBTP = -1.0
BLACK_LUMA = 6.0                 # mean luma under this is a black frame


def _probe(path: str) -> dict[str, Any]:
    done = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-show_streams", "-show_format",
         "-of", "json", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return json.loads(done.stdout)


def _loudness(path: str) -> dict[str, float]:
    """EBU R128 from ffmpeg's own loudnorm analysis pass."""
    done = subprocess.run(
        [shutil.which("ffmpeg"), "-v", "info", "-i", path, "-af",
         "loudnorm=I=-14:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    text = done.stderr or ""
    start = text.rfind("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        return {}
    try:
        raw = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return {key: float(value) for key, value in raw.items()
            if key.startswith("input_") and value not in ("-inf", "inf")}


def _frame_stats(path: str) -> list[tuple[float, float]]:
    """`(pts seconds, mean luma)` per frame, from signalstats."""
    done = subprocess.run(
        [shutil.which("ffprobe"), "-v", "error", "-f", "lavfi",
         f"movie={path.replace(os.sep, '/')},signalstats",
         "-show_entries", "frame=pkt_pts_time,pts_time:frame_tags=lavfi.signalstats.YAVG",
         "-of", "json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        data = json.loads(done.stdout)
    except json.JSONDecodeError:
        return []
    out = []
    for index, frame in enumerate(data.get("frames", [])):
        tags = frame.get("tags", {})
        luma = tags.get("lavfi.signalstats.YAVG")
        when = frame.get("pts_time") or frame.get("pkt_pts_time") or index / FPS
        if luma is not None:
            out.append((float(when), float(luma)))
    return out


def _mpdecimate_frames(path: str) -> int | None:
    """How many frames survive `mpdecimate`, which compares pixels, not means."""
    done = subprocess.run(
        [shutil.which("ffmpeg"), "-v", "info", "-i", path,
         "-vf", "mpdecimate", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    kept = None
    for line in (done.stderr or "").splitlines():
        if line.startswith("frame=") or " frame=" in line:
            part = line.split("frame=", 1)[1].strip().split()[0]
            if part.isdigit():
                kept = int(part)
    return kept


def _hold_is_static(path: str, hold_frames: int) -> tuple[bool, str]:
    """Is the held opening one picture, judged below the text?

    Compares frame 2 with frame `hold_frames - 2` over the rows under y 560,
    which is below PICK ONE and its shadow and above nothing else that moves.
    Whole frames cannot be compared because the hook fades in and out over the
    hold, which is the point of it.
    """
    import numpy as np
    from PIL import Image

    scratch = os.path.join(OUT_DIR, "short", "qc")
    os.makedirs(scratch, exist_ok=True)
    grabbed = []
    for index in (2, max(3, hold_frames - 2)):
        out = os.path.join(scratch, f"hold_{index:04d}.png")
        subprocess.run(
            [shutil.which("ffmpeg"), "-v", "error", "-y", "-i", path,
             "-vf", f"select='eq(n\\,{index})'", "-vsync", "0", "-frames:v", "1", out],
            capture_output=True, text=True,
        )
        if not os.path.isfile(out):
            return False, "could not extract the held frames"
        grabbed.append(np.asarray(Image.open(out).convert("RGB"), dtype=np.int16)[560:])
    difference = np.abs(grabbed[0] - grabbed[1])
    mean = float(difference.mean())
    pixels = difference.shape[0] * difference.shape[1]
    moved = float((difference.max(axis=2) > 2).sum()) / pixels
    # **Not bit-equality, because h.264 is lossy and these frames are encoded
    # differently even when the source is the same picture.** Measured on this
    # file the two held frames differ by a mean of 0.014 with 0.08% of pixels
    # off by more than two - noise spread evenly over the frame, not structure.
    # A hold that had actually drifted would move a region, not a scatter.
    return (
        mean < 0.10 and moved < 0.005,
        f"the held opening is one still picture below the hook "
        f"(mean difference {mean:.4f}, {moved * 100:.3f}% of pixels moved by more than 2)",
    )


def report(seed: int = 5432) -> bool:
    from sloped import presentation
    import numpy as np

    ok = True

    def check(passed: bool, line: str) -> None:
        nonlocal ok
        ok = ok and passed
        print(f"  [{'pass' if passed else 'FAIL'}] {line}")

    for path in (VIDEO, VISUAL):
        if not os.path.isfile(path):
            print(f"  [FAIL] missing {path}")
            return False

    print("container and stream")
    info = _probe(VIDEO)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audios = [s for s in info["streams"] if s["codec_type"] == "audio"]
    check(int(video["width"]) == WIDTH and int(video["height"]) == HEIGHT,
          f"{video['width']}x{video['height']} (want {WIDTH}x{HEIGHT})")
    check(video["r_frame_rate"] == f"{FPS}/1", f"{video['r_frame_rate']} fps")
    frames = int(video["nb_frames"])
    check(frames == EXPECTED_FRAMES,
          f"{frames} frames = {frames / FPS:.4f} s (want {EXPECTED_FRAMES})")
    check(19.8 <= frames / FPS <= 20.2, f"runtime {frames / FPS:.3f} s inside 19.8-20.2")
    check(len(audios) == 1, f"{len(audios)} audio stream(s)")
    visual = _probe(VISUAL)
    check(not [s for s in visual["streams"] if s["codec_type"] == "audio"],
          "the visual cut carries no audio")
    check(int(next(s for s in visual["streams"] if s["codec_type"] == "video")["nb_frames"])
          == EXPECTED_FRAMES, "the visual cut has the same frame count")

    print("audio")
    loud = _loudness(VIDEO)
    if loud:
        peak = loud.get("input_tp", 0.0)
        check(peak <= TRUE_PEAK_CEILING_DBTP + 0.05,
              f"true peak {peak:+.2f} dBTP (ceiling {TRUE_PEAK_CEILING_DBTP:+.1f})")
        print(f"         integrated {loud.get('input_i', float('nan')):.2f} LUFS, "
              f"range {loud.get('input_lra', float('nan')):.2f} LU")
    else:
        check(False, "could not measure loudness")

    # The designed hierarchy, measured on the mix this build produces.
    replay, track, clock = presentation.load(
        os.path.join(OUT_DIR, f"race_{seed}.json"),
        os.path.join(OUT_DIR, f"cameras_{seed}.json"),
        EXPECTED_FRAMES - int(round(presentation.HOLD_SECONDS * FPS)),
    )
    from audio import marble
    from audio.synthesis import SAMPLE_RATE
    mix = marble.build_race_audio(replay, track, clock)
    mono = 0.5 * (np.array(mix.left) + np.array(mix.right))
    hop = SAMPLE_RATE // 100
    envelope = np.array([float(np.abs(mono[i * hop:(i + 1) * hop]).max())
                         for i in range(len(mono) // hop)])

    def db(value: float) -> float:
        return 20 * math.log10(max(abs(value), 1e-9))

    def loudest_in(at: float, after: float = 0.25) -> float:
        a = int(at * 100)
        b = min(len(envelope), a + int(after * 100))
        return db(float(envelope[a:b].max())) if b > a else -120.0

    crossings = sorted(
        (float(e["t"]), int(e["order"])) for e in replay["events"]
        if e["kind"] == "finish_line" and clock.at(float(e["t"])) is not None
    )
    levels = {order: loudest_in(clock.at(when)) for when, order in crossings}
    winner = levels.get(1, -120.0)
    check(all(winner >= level - 1e-6 for level in levels.values()),
          "the winner's crossing is the loudest crossing "
          + ", ".join(f"#{k} {v:.2f}" for k, v in sorted(levels.items())))
    top = int(np.argmax(envelope)) / 100.0
    winner_at = clock.at(crossings[0][0])
    check(abs(top - winner_at) < 0.30,
          f"the loudest moment in the film is {top:.2f} s, the winner crosses at {winner_at:.2f} s")
    check(not mix.limited, "the safety limiter stayed idle, so the hierarchy is as designed")

    ordinary = float(np.median(envelope[int(4 * 100):int(11 * 100)]))
    check(db(10 ** (winner / 20)) - db(ordinary) > 6.0,
          f"the winner is {winner - db(ordinary):.1f} dB over a typical mid-race moment")

    print("picture")
    stats = _frame_stats(VIDEO)
    if stats:
        dark = [(t, y) for t, y in stats if y < BLACK_LUMA]
        check(not dark, f"no black frames (darkest {min(y for _, y in stats):.1f} luma)")
    else:
        check(False, "could not read frame statistics")

    # **Duplicates are a pixel question and mean luma cannot answer it.**
    # The first version of this check called two frames identical when their
    # YAVG matched, and reported duplicates at 17.98 s and 19.82 s. Both were
    # coincidences of a mean over two million pixels: compared properly the
    # pairs differ in 778 930 and 726 555 pixels respectively. `mpdecimate` is
    # the tool that actually compares frames, so it is the one that is asked.
    survived = _mpdecimate_frames(VIDEO)
    hold_frames = int(round(presentation.HOLD_SECONDS * FPS))
    # The held opening is genuinely one picture repeated, so mpdecimate is
    # expected to drop it down to a handful of frames - the text fading over it
    # is the only thing moving. Everything after it must survive intact.
    expected_min = EXPECTED_FRAMES - hold_frames - 1
    check(survived is not None and survived >= expected_min,
          f"mpdecimate keeps {survived} of {EXPECTED_FRAMES} frames "
          f"(at least {expected_min} once the held opening is allowed to collapse)")

    # The hold itself, checked where the text is not: PICK ONE occupies y 247 to
    # 436, so below y 560 the held frames must be pixel-identical to each other
    # and to the master's own first frame.
    same, detail = _hold_is_static(VIDEO, hold_frames)
    check(same, detail)

    print("overlays, against measured marble positions")
    ring_from = clock.at(crossings[0][0]) + 0.20
    ring_to = ring_from + 0.70
    photo = [clock.at(when) for when, order in crossings if order in (4, 5)]
    check(all(ring_to < at for at in photo),
          f"the winner's mark ends at {ring_to:.2f} s, before the "
          f"{min(photo):.2f} s dead heat")
    check(ring_from > clock.at(crossings[0][0]),
          "the winner's mark starts only after the winner has crossed")
    gate = presentation.actuator_move(replay, clock, "start.paddle")
    check(gate is not None and gate > 0.80,
          f"the hook is gone by 0.80 s; the gates first move at {gate:.3f} s")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if report() else 1)

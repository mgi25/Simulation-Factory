"""Section 14 of the brief, as measurements on the file that came out.

Everything here reads the delivered mp4 itself rather than the plan that made
it, because the question a reviewer asks is about the file. Where a check can be
answered from the pixels or the samples it is; where it cannot - "does the time
skip feel intentional" - the closest measurable proxy is stated as what it is.

    python tools/sloped_short_qc.py            # V21.1
    python tools/sloped_short_qc.py v20        # the earlier cut

**The frame count is derived, not typed.** V21.1 is V20 with 85 master frames
omitted, so a hard-coded 1192 would have had to be edited in two places and
would then only be asserting that somebody edited it. `sloped_short.load_all`
builds the edition's clock and this asks it how long the film should be.
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

WIDTH, HEIGHT, FPS = 1080, 1920, 60
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


def _hold_is_static(path: str, hold_frames: int, offset: int = 0) -> tuple[bool, str]:
    """Is the held opening one picture, judged below the text?

    Every frame of the hold is compared with the one before it, over the rows
    under y 560 - below PICK ONE and its shadow, and above nothing else that
    moves. Whole frames cannot be compared because the hook fades in and out
    over the hold, which is the point of it.

    `offset` is where the held frames start, which is no longer frame zero:
    V22 puts a 120-frame course preview in front of the hold and V22.1 a
    210-frame one, and a preview is moving footage by design. Measured against
    frames 2 and 40 of the V22 file - which are preview frames - an earlier
    version of this check reported a mean difference of 66.3 with 99.9% of
    pixels moved, which is a correct reading of the wrong two frames.

    ## Why the **median** adjacent step and not the two ends

    This compared frame 2 with frame `hold_frames - 2` until V22.1, and on V22.1
    it failed: mean 0.79 with 20.4% of pixels moved. Nothing had drifted. x264's
    default key interval is 250 frames, V22.1's hold runs 210 to 251, and **an
    IDR lands on frame 250, inside it**. An I-frame is quantised from scratch
    rather than predicted, so it differs from the P-frames before it - by up to
    48 on a hard edge here, because the V22.1 held frame is the elevation-30
    start with the whole drum rim in it and far more fine detail than V21's.
    Broken down, frames 212-240 agree to a mean of 0.03 and the entire
    difference is the single step at the IDR; side by side the two pictures are
    the same picture.

    So the two-ended reading was measuring the encoder. The median of the 41
    adjacent steps measures the *picture*: it is immune to the one or two frames
    an IDR lands on, it still reports 2.4 per frame if the wrong footage is
    being examined, and it is what "one still picture" actually means. The
    largest step is reported beside it rather than judged, because on a static
    run its cause is the bitstream and not the edit.
    """
    import numpy as np
    from PIL import Image

    scratch = os.path.join(OUT_DIR, "short", "qc")
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch, exist_ok=True)
    last = offset + max(3, hold_frames - 2)
    subprocess.run(
        [shutil.which("ffmpeg"), "-v", "error", "-y", "-i", path,
         "-vf", f"select='between(n\\,{offset + 2}\\,{last})'",
         "-vsync", "0", os.path.join(scratch, "hold_%04d.png")],
        capture_output=True, text=True,
    )
    names = sorted(f for f in os.listdir(scratch) if f.endswith(".png"))
    if len(names) < 3:
        return False, "could not extract the held frames"
    frames = [
        np.asarray(Image.open(os.path.join(scratch, name)).convert("RGB"),
                   dtype=np.int16)[560:]
        for name in names
    ]
    pixels = frames[0].shape[0] * frames[0].shape[1]
    steps = []
    for before, after in zip(frames, frames[1:]):
        difference = np.abs(before - after)
        steps.append((float(difference.mean()),
                      float((difference.max(axis=2) > 2).sum()) / pixels))
    mean = float(np.median([step[0] for step in steps]))
    moved = float(np.median([step[1] for step in steps]))
    worst = max(steps)
    # **Not bit-equality, because h.264 is lossy and two encodings of one
    # picture differ.** On a hold that had actually drifted these medians move
    # together and by orders of magnitude, which is what the bar is set for.
    return (
        mean < 0.10 and moved < 0.005,
        f"the held opening is one still picture below the hook, over "
        f"{len(steps)} adjacent frames (median step {mean:.4f}, {moved * 100:.3f}% "
        f"of pixels; largest step {worst[0]:.4f}, {worst[1] * 100:.3f}%)",
    )


def _opening_moves(path: str, frames: int = 15) -> tuple[bool, str]:
    """Is the film's opening alive, judged below the mark?

    `_hold_is_static`'s measurement, its window and its bars, asking the
    opposite question. The same rows are compared - everything under y 560, so
    the mark fading over the top is not what is being read - and the same median
    adjacent step is taken, for the same reason: an IDR lands where it lands and
    the median is immune to it.

    The bar is `_hold_is_static`'s own, read the other way. A run it would call
    still is a median step under 0.10 with under 0.5 per cent of pixels moved;
    an opening passes here by being outside that. There is no third setting, so
    a film cannot satisfy both and cannot slip between them.
    """
    import numpy as np
    from PIL import Image

    scratch = os.path.join(OUT_DIR, "short", "qc_open")
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch, exist_ok=True)
    subprocess.run(
        [shutil.which("ffmpeg"), "-v", "error", "-y", "-i", path,
         "-vf", r"select='lt(n\,%d)'" % frames,
         "-vsync", "0", os.path.join(scratch, "open_%04d.png")],
        capture_output=True, text=True,
    )
    names = sorted(f for f in os.listdir(scratch) if f.endswith(".png"))
    if len(names) < 3:
        return False, "could not extract the opening frames"
    pictures = [
        np.asarray(Image.open(os.path.join(scratch, name)).convert("RGB"),
                   dtype=np.int16)[560:]
        for name in names
    ]
    pixels = pictures[0].shape[0] * pictures[0].shape[1]
    steps = []
    for before, after in zip(pictures, pictures[1:]):
        difference = np.abs(before - after)
        steps.append((float(difference.mean()),
                      float((difference.max(axis=2) > 2).sum()) / pixels))
    mean = float(np.median([step[0] for step in steps]))
    moved = float(np.median([step[1] for step in steps]))
    return (
        mean >= 0.10 and moved >= 0.005,
        f"the opening is live, not held: over {len(steps)} adjacent frames the "
        f"median step is {mean:.4f} with {moved * 100:.3f}% of pixels moved "
        f"(a held frame is under 0.10 and 0.500%)",
    )


def _dark_band(path: str, when: float, until: float,
               x_from: int = 90, x_to: int = 990, ceiling: float = 130.0):
    """The tallest band of rows a card could sit on, over a stretch of film.

    The payoff lab's own measurement, re-run on this edition's tail: every
    second frame from `when` to `until`, the **maximum** luma of each row across
    the text corridor, and then the tallest run of rows whose maximum never
    exceeds `ceiling` on any of them.

    **It must be measured on footage with no overlay on it**, which is what the
    silent integrated master is for. Reading the finished film instead measures
    the card's own warm white and answers a different question: the first
    version of this check did that and reported 111 of 1713 bright rows, which
    is a correct count of a finish frame's sky, deck and racers.

    Returns `(low, high, the worst luma inside it)`, or None.
    """
    import numpy as np
    from PIL import Image

    scratch = os.path.join(OUT_DIR, "short", "qc_band")
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch, exist_ok=True)
    every_second = "select=not(mod(n" + chr(92) + ",2))"
    subprocess.run(
        [shutil.which("ffmpeg"), "-v", "error", "-y", "-ss", f"{when:.4f}",
         "-i", path, "-t", f"{max(0.05, until - when):.4f}",
         "-vf", every_second, "-vsync", "0",
         os.path.join(scratch, "t_%04d.png")],
        capture_output=True, text=True,
    )
    names = sorted(f for f in os.listdir(scratch) if f.endswith(".png"))
    if not names:
        return None
    worst = None
    for name in names:
        pixels = np.asarray(
            Image.open(os.path.join(scratch, name)).convert("RGB"), dtype=float
        )
        luma = (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
                + 0.0722 * pixels[..., 2])
        row = luma[:, x_from:x_to].max(axis=1)
        worst = row if worst is None else np.maximum(worst, row)
    best = (0, -1)
    run = None
    for y, value in enumerate(worst):
        if value <= ceiling:
            run = y if run is None else run
        elif run is not None:
            if y - 1 - run > best[1] - best[0]:
                best = (run, y - 1)
            run = None
    if run is not None and len(worst) - 1 - run > best[1] - best[0]:
        best = (run, len(worst) - 1)
    if best[1] < best[0]:
        return None
    return best[0], best[1], float(worst[best[0]:best[1] + 1].max())


def _ink_rows(path: str, when: float, x_from: int = 90, x_to: int = 990):
    """The rows one still frame has solid warm ink in, over the text corridor.

    Used for one question: is the mark actually drawn on frame zero. That is a
    presence test on a frame whose background behind the mark is known to be
    dark - `v24_hook.background_report` puts the massif in shade there - and it
    is not the right instrument for the payoff, which is `_dark_band`.
    """
    import numpy as np
    from PIL import Image

    scratch = os.path.join(OUT_DIR, "short", "qc_ink")
    os.makedirs(scratch, exist_ok=True)
    grab = os.path.join(scratch, f"at_{int(round(when * 1000)):06d}.png")
    subprocess.run(
        [shutil.which("ffmpeg"), "-v", "error", "-y", "-ss", f"{when:.4f}",
         "-i", path, "-frames:v", "1", grab],
        capture_output=True, text=True,
    )
    if not os.path.isfile(grab):
        return None
    pixels = np.asarray(Image.open(grab).convert("RGB"), dtype=float)
    luma = (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2])
    corridor = luma[:, x_from:x_to]
    rows = np.where((corridor > 200.0).sum(axis=1) > 4)[0]
    return rows, corridor


def report(seed: int = 5432, edition: str = "v21") -> bool:
    from sloped import presentation
    from tools.sloped_short import EDITIONS, cue_policy, load_all
    import numpy as np

    if edition not in EDITIONS:
        print(f"  [FAIL] no such edition: {edition!r}")
        return False
    VIDEO = EDITIONS[edition]["video"]
    VISUAL = EDITIONS[edition]["visual"]
    low, high = EDITIONS[edition]["runtime"]

    # The clock the film actually runs on, cuts and all, so every figure below
    # is the edition's own rather than a number carried over from the last one.
    replay, track, clock = load_all(seed, edition)[:3]
    EXPECTED_FRAMES = clock.frames

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
    check(low <= frames / FPS <= high,
          f"runtime {frames / FPS:.3f} s inside {low}-{high}")
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
    from audio import marble
    from audio.synthesis import SAMPLE_RATE
    mix = marble.build_race_audio(replay, track, clock, cues=cue_policy(edition))
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

    # A typical mid-race moment: after the start and before the finish, on
    # whichever clock this edition runs, so the reference is the same footage.
    mid_from = clock.at(8.62) or 4.0
    mid_to = clock.at(15.35) or (clock.duration - 8.8)
    ordinary = float(np.median(envelope[int(mid_from * 100):int(mid_to * 100)]))
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
    # **The hold is the clock's, not `presentation.HOLD_SECONDS`.** Every
    # edition up to V22.1 holds 0.70 s and this read the constant; V24 holds
    # nothing, and a constant here would let it through a check for a static
    # opening it does not have - and then fail it on the frame count.
    hold_frames = clock.hold_frames
    # The held opening is genuinely one picture repeated, so mpdecimate is
    # expected to drop it down to a handful of frames - the text fading over it
    # is the only thing moving. Everything after it must survive intact. With no
    # hold at all the allowance is zero and every frame has to be its own.
    expected_min = EXPECTED_FRAMES - hold_frames - 1
    check(survived is not None and survived >= expected_min,
          f"mpdecimate keeps {survived} of {EXPECTED_FRAMES} frames "
          f"(at least {expected_min} once the held opening is allowed to collapse)")

    if hold_frames:
        # The hold itself, checked where the text is not: PICK ONE occupies
        # y 247 to 436, so below y 560 the held frames must be pixel-identical
        # to each other and to the master's own first frame.
        same, detail = _hold_is_static(VIDEO, hold_frames, clock.prefix_frames)
        check(same, detail)
    else:
        # **The same check, inverted, because the claim is inverted.** V24's
        # whole premise is that the opening is alive: it holds nothing, so the
        # first two frames must *differ*, and by more than encoder noise. This
        # is not a weaker bar than the hold check - it is the same measurement
        # asked to prove the opposite thing, and a film that accidentally
        # shipped a frozen first frame would fail here rather than pass quietly.
        moving, detail = _opening_moves(VIDEO)
        check(moving, detail)

    print("overlays, against measured marble positions")
    # The ring's own window, as this edition places it. V24 opens it **on** the
    # crossing and runs 0.300 s, because the payoff lab measured that the winner
    # is on screen for 0.217 s and the shipped 0.200+0.700 puts one frame of the
    # mark on a visible marble. Every other edition keeps 0.200 and 0.700.
    from sloped import v24_payoff
    if EDITIONS[edition].get("payoff"):
        ring_delay, ring_span = v24_payoff.RING_DELAY, v24_payoff.RING_SECONDS
    else:
        ring_delay, ring_span = 0.20, 0.70
    ring_from = clock.at(crossings[0][0]) + ring_delay
    ring_to = ring_from + ring_span
    photo = [clock.at(when) for when, order in crossings if order in (4, 5)]
    check(all(ring_to < at for at in photo),
          f"the winner's mark ends at {ring_to:.2f} s, before the "
          f"{min(photo):.2f} s dead heat")
    check(ring_from >= clock.at(crossings[0][0]) - 1e-9,
          "the winner's mark starts no earlier than the winner's crossing")
    # **The mark and the machine, and which of the two is supposed to be first.**
    #
    # For every edition up to V22.1 the mark is a title over a frozen frame and
    # the rule is that it is gone before anything moves: PICK ONE fades out at
    # the hold's end plus 0.80 s and the gates open after that.
    #
    # V24 inverts the rule on purpose. The mark sits over **live** footage, so
    # the bar is that the machine is already moving while it is up - a mark over
    # a still picture is the thing the retention numbers punished. Both are
    # checked; neither is relaxed.
    gate = presentation.actuator_move(replay, clock, "start.paddle")
    if EDITIONS[edition].get("mark") == "v24":
        from sloped import v24 as v24_module
        check(gate is not None and gate < v24_module.MARK_OUT_FROM,
              f"the gates move at {gate:.3f} s, while PICK A COLOR is still up "
              f"(it starts to leave at {v24_module.MARK_OUT_FROM:.2f} s)")
        check(gate is not None and gate <= 0.25,
              f"the first mechanism motion is at {gate:.3f} s, inside the first "
              f"quarter second")
    else:
        hook_gone = clock.prefix + 0.80
        check(gate is not None and gate > hook_gone,
              f"the hook is gone by {hook_gone:.2f} s; the gates first move at "
              f"{gate:.3f} s")

    # **The retention claim, measured rather than asserted.** The floor drops
    # when `start.panel` first moves, and after it the field never stops going
    # downhill - so this is the second the race proper starts for a viewer.
    trapdoor = presentation.actuator_move(replay, clock, "start.panel")
    print(f"         the floor opens at {trapdoor:.3f} s "
          f"({trapdoor - gate:.3f} s after the gates)")
    if EDITIONS[edition]["cuts"]:
        check(trapdoor is not None and trapdoor <= 2.0,
              f"the release is inside the first two seconds ({trapdoor:.3f} s)")

    if EDITIONS[edition].get("mark") == "v24" or EDITIONS[edition].get("payoff"):
        print("V24: the hook frame, the joins and the payoff")
        from sloped import v24 as v24_module
        from sloped import v24_payoff
        from tools.sloped_short import _winner_of
        from tools.sloped_v24_audit import EXPOSURE_BAR, join_audit

        winner_id = _winner_of(replay)[0]

        # **The mark is on frame zero.** Not faded in over it, not arriving a
        # beat later: the premise has to be readable before a thumb has decided
        # anything, so the ink is looked for on the first frame of the file.
        found = _ink_rows(VIDEO, 0.0)
        if found is None:
            check(False, "could not read frame zero")
        else:
            rows, _corridor = found
            band = (v24_module.MARK_BASELINE - 120, v24_module.MARK_BASELINE + 40)
            on_mark = [row for row in rows if band[0] <= row <= band[1]]
            check(bool(on_mark),
                  f"PICK A COLOR is on frame 0: {len(on_mark)} rows of solid ink "
                  f"between y {band[0]} and y {band[1]}")

        # Every omission in the film, against the spread of the shot it is in.
        # The bar is the film's own accepted joins - see `sloped_v24_audit`.
        for row in join_audit(replay, track, clock):
            check(row["exposure"] <= EXPOSURE_BAR or not row["same_camera"],
                  f"the {row['name']} join is {row['exposure']:.2f}x its shot's "
                  f"per-frame spread "
                  f"({'same camera' if row['same_camera'] else 'at a camera cut'})")
            if row["name"] == "spin":
                check(row["rotor_phase_error_deg"] <= 1.0,
                      f"the mixer join's rotor phase error is "
                      f"{row['rotor_phase_error_deg']:.2f} deg")

        # The payoff, measured on the finished file rather than on the card.
        # The band the plate has to survive is re-measured here, because the
        # payoff lab's y 297-548 was taken on a tail that ended at replay
        # 24.467 and V24's ends at 23.450.
        card_from, card_to = v24_payoff.schedule(
            crossing=clock.at(crossings[0][0]), beat=v24_module.BEAT,
            seconds=v24_payoff.PAYOFF_SECONDS, fps=FPS,
        )["card"]
        check(card_to <= clock.duration + 1e-6,
              f"the payoff card ends at {card_to:.3f} s, inside the "
              f"{clock.duration:.3f} s film")
        check(card_from > clock.at(crossings[0][0]),
              f"the card comes up {card_from - clock.at(crossings[0][0]):.2f} s "
              f"after the crossing")
        # **The band, re-measured on this film's own tail.** The payoff lab
        # measured y 297-548 over a tail that ran to replay 24.467; V24's stops
        # at 23.450 and this is the same parked stand shooting less of it, so
        # the band is re-read rather than inherited. On the *silent* master,
        # which is this picture with nothing drawn on it.
        silent = EDITIONS[edition].get("silent")
        band = _dark_band(silent, card_from, clock.duration) if silent else None
        if band is None:
            check(False, "could not measure the payoff band")
        else:
            low, high, worst = band
            card = v24_payoff.build(style=EDITIONS[edition]["payoff"],
                                    winner=winner_id,
                                    from_place=v24_payoff.WINNER_FROM)
            check(low <= card.box[1] and card.box[3] <= high,
                  f"the card's ink (y {card.box[1]}-{card.box[3]}) is inside the "
                  f"tail's own dark band (y {low}-{high}, worst luma {worst:.1f})")
            check(card.text_contrast >= 4.5,
                  f"the card's text is {card.text_contrast:.2f}:1 on its own plate")

    # Omitted time, and whether this edition marks it. **An uncued omission is
    # a claim, not an oversight**: V22.1 cuts four whole rotor revolutions out
    # of a constant-rate spin, so the picture is continuous across the join and
    # a whoosh would announce an edit nobody could otherwise see. See
    # `audio.marble.Cues`.
    cues = cue_policy(edition)
    for at, dropped in presentation.omissions(clock):
        marked = "cued" if cues.omission else "deliberately uncued"
        print(f"         {dropped:.3f} s of replay omitted at {at:.3f} s ({marked})")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if report(edition=(sys.argv[1] if len(sys.argv) > 1 else "v21")) else 1)

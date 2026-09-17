"""Race #2's finished film: the clock, the three marks, and the evidence for them.

V31 proved the camera, V31.1 the track, V30.1 the room. None of them is touched
here. What was missing was the layer between a rendered clip and something a
viewer watches on a phone: an opening that says what the format is, a mark that
says which ball won, a card that says what it did, and a soundtrack.

Race #1 has all four in `sloped.presentation`, `sloped.overlays`,
`sloped.v24_hook`, `sloped.v24_payoff` and `audio.marble`. **Every one of them
is imported rather than restated.** This module is the adapter that lets them
read a Race #2 film, plus the three placements that have to be measured against
*this* picture because a placement measured on another film is a guess.

## The clock, and why Race #2's is a single segment

`sloped.presentation.Clock` maps replay seconds to finished-film seconds through
an edit map. Race #1 has one because its master holds its first frame for 42
frames and cuts 85 frames out of the middle of the start.

**Race #2 has no edit map at all.** `race2.rig.write_track` emits `cuts` - camera
changes - and no `edit`, and `race2_render.gd` walks output frame `i` at replay
second `i / fps` from 0 to `round(duration * fps)` inclusive. Output second and
replay second are the same number for the whole film. So the clock is one
segment of slope one, `hold` is zero and `prefix` is zero, and the film has
**zero temporal omissions by construction** rather than by assertion:
`pres.omissions()` reads the gaps between segments and there is only one segment.

That is also why `master_frames` is 1150 and not 1149. The track's `duration` is
19.15 s, and the renderer's `range(first, last + 1)` over `round(19.15 * 60)`
writes frames 0 to 1149. The film is 1150 frames, which is 19.1667 s, and the
soundtrack is built to `Clock.duration` so it is exactly 1150 x 800 samples.
Taking the nominal 19.15 would make the audio one frame short of the picture.

## What is measured here rather than chosen

Three things, and each of them was wrong when it was carried over unmeasured:

* **the hook's size and baselines.** V24's mark is one line because it was sized
  against V20's held opening frame. This opening is live footage with eight
  racers low in the picture, and the band above them is 640 px tall - room for a
  mark twice the height of the one V31's preview used. `hook_placement` fits the
  type to the frame's own gutter and centres it in the band the racers leave.
* **the ring's window.** V24's payoff lab found both shipped winner marks
  pointing at a marble behind the finish gantry. `ring_track` runs the same
  occlusion test over the mark's whole life and reports every frame.
* **the card's band.** V24's `PAYOFF_BAND` is `(297, 548)`, measured on Race
  #1's finish lens. On this film that band has racers in it for the whole of the
  card's life and peaks at 255 luma. `card_band` measures the real one.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Sequence

from sloped import overlays, v24_payoff
from sloped.presentation import Clock

__all__ = [
    "CARD_BEAT",
    "DELIVERY",
    "FPS",
    "HOOK_CLEARANCE",
    "HOOK_GUTTER",
    "HOOK_IN",
    "HOOK_LEAD",
    "HOOK_OUT_FROM",
    "HOOK_OUT_TO",
    "HOOK_TEXT",
    "HOOK_TOP",
    "RING_DELAY",
    "RING_SECONDS",
    "card_band",
    "card_plate",
    "comeback_rank",
    "film_clock",
    "hook_placement",
    "hook_plate",
    "load_film",
    "rank_runs",
    "ring_track",
    "winner_of",
]

FPS = 60
DELIVERY = (1080, 1920)


# --- the clock --------------------------------------------------------------


def film_clock(track: dict[str, Any], master_frames: int | None = None) -> Clock:
    """The finished film's clock for a Race #2 camera track.

    One segment, no hold, no prefix: see the module docstring. `master_frames`
    defaults to the renderer's own rule, `round(duration * fps) + 1`.
    """
    duration = float(track["duration"])
    fps = int(track.get("fps", FPS))
    if master_frames is None:
        master_frames = int(round(duration * fps)) + 1
    return Clock(
        segments=((0.0, duration, 0.0, duration),),
        hold=0.0,
        fps=fps,
        master_frames=master_frames,
        prefix=0.0,
    )


def load_film(
    replay_path: str, track_path: str, master_frames: int | None = None
) -> tuple[dict[str, Any], dict[str, Any], Clock]:
    """The replay, the camera track and the clock that joins them."""
    with open(replay_path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    with open(track_path, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    return replay, track, film_clock(track, master_frames)


# --- who won, and what it did -----------------------------------------------


def winner_of(replay: dict[str, Any]) -> tuple[int, float]:
    """`(marble, replay second)` of the first crossing, from the replay itself.

    Read off the `finish_line` events rather than from a re-run, so the winner
    the marks point at is the winner the rendered frames show.
    """
    crossings = [
        (float(event["t"]), int(event["id"]))
        for event in replay.get("events", ())
        if event["kind"] == "finish_line" and int(event["order"]) == 1
    ]
    if not crossings:
        raise ValueError("the replay has no first crossing")
    when, marble = min(crossings)
    return marble, when


def rank_runs(
    rank_series: Sequence[tuple[float, Sequence[int]]], marble: int, until: float
) -> list[tuple[float, float, int]]:
    """One marble's rank history as contiguous `(from, to, rank)` runs.

    Clipped to `until`, because a rank the marble held after the film ended is
    not part of any story the film can tell.
    """
    rows = [
        (float(when), list(order).index(marble) + 1)
        for when, order in rank_series
        if marble in order and float(when) <= until + 1e-9
    ]
    runs: list[list[float | int]] = []
    for when, rank in rows:
        if runs and runs[-1][2] == rank:
            runs[-1][1] = when
        else:
            runs.append([when, when, rank])
    return [(float(a), float(b), int(r)) for a, b, r in runs]


# How long a rank has to be held before the film may claim the marble was in it.
#
# **This exists because the shipped claim was an artefact.** V31's preview reads
# the worst index the winner ever occupies in `rank_series` and prints it, which
# on this seed is 6th - and the winner holds 6th for **0.217 s**, one run of 13
# samples out of 1149, at 3.13 s. Every other instrument disagrees: the race's
# own checkpoint ladder records `{release: 4, first_event: 5, quarter: 4,
# half: 3, three_quarter: 2}`, and the duration-weighted history gives 5th four
# separate times for 1.62 s in total, the longest run 0.933 s.
#
# Half a second is 30 frames. A rank the marble held for fewer than that is a
# sample of a scramble, not a position a viewer could see it in, and a card that
# names it is a fabricated comeback. `comeback_rank` is therefore a floor rather
# than a maximum, and it reports what it rejected.
COMEBACK_FLOOR = 0.5


def comeback_rank(
    runs: Sequence[tuple[float, float, int]],
    checkpoints: dict[str, int] | None = None,
    floor: float = COMEBACK_FLOOR,
    fps: int = FPS,
) -> dict[str, Any]:
    """The deepest rank the winner actually held, with what was rejected.

    Two independent instruments have to agree before the number is used: the
    duration-weighted rank history and, when it is given, the race's own
    checkpoint ladder. They do on this seed, at 5th. If they ever did not, the
    caller sees both and the report says so rather than picking one.
    """
    held: dict[int, float] = {}
    longest: dict[int, float] = {}
    for start, stop, rank in runs:
        span = stop - start + 1.0 / fps
        held[rank] = held.get(rank, 0.0) + span
        longest[rank] = max(longest.get(rank, 0.0), span)

    deepest_any = max(held) if held else 1
    qualifying = [rank for rank in held if longest[rank] >= floor - 1e-9]
    deepest_held = max(qualifying) if qualifying else 1
    rejected = [
        {
            "rank": rank,
            "seconds_total": round(held[rank], 4),
            "longest_run": round(longest[rank], 4),
            "frames_longest": int(round(longest[rank] * fps)),
        }
        for rank in sorted(held, reverse=True)
        if rank > deepest_held
    ]
    checkpoint_worst = max(checkpoints.values()) if checkpoints else None
    return {
        "rank": deepest_held,
        "floor_seconds": floor,
        "seconds_at_rank": round(held.get(deepest_held, 0.0), 4),
        "longest_run_at_rank": round(longest.get(deepest_held, 0.0), 4),
        "deepest_instant_rank": deepest_any,
        "rejected": rejected,
        "checkpoints": dict(checkpoints) if checkpoints else None,
        "checkpoint_worst": checkpoint_worst,
        "instruments_agree": checkpoint_worst is None or checkpoint_worst == deepest_held,
        "held_seconds": {rank: round(value, 4) for rank, value in sorted(held.items())},
    }


# --- the hook ---------------------------------------------------------------

HOOK_TEXT = "PICK A COLOR"

# V24's timing, unchanged, and it is the whole of Part B. The mark is up on
# frame zero over live footage - there is no held frame to fade it in over - and
# it is gone by 1.30 s. The first camera cut on this film is at 2.233 s, so the
# mark clears the cut by 0.93 s and never runs into the racing.
HOOK_IN = 0.0
HOOK_OUT_FROM = 1.05
HOOK_OUT_TO = 1.30

# **The mark is set in two lines, and the reason is a measurement.**
#
# V24 set PICK A COLOR at 96 pt in one line because it was sized against a 1080
# frame with `pick_one`'s eight-per-cent gutter. Measured on the delivered face,
# that line is 785 px of ink with 13.5% clear each side, and its cap height is
# 71 px - **17.8 px at the 270x480 a phone feed scrubs at**. V31's preview ran
# the same line at 104, which is 19.2 px.
#
# This opening is not V20's held frame. The eight racers sit low - measured over
# the mark's whole life, their topmost pixel is y 806 - which leaves a usable
# band of 640 px above them once the frame's gutter and V24's clearance are
# taken off, and a two-line block uses it: at the same 13.5% gutter the widest
# of `PICK A` and `COLOR` sets at 201 pt, a 148 px cap, **37.0 px at 270x480**.
# Same face, same warm white, same soft shadow, same twelve glyphs, through
# `overlays._shadowed`. Only the break is new.
HOOK_GUTTER = 0.135          # of the frame width, each side: V24's shipped margin
HOOK_LEAD = 1.15             # baseline to baseline, as a multiple of the size
HOOK_TOP = 96                # the frame's own gutter, applied vertically
HOOK_CLEARANCE = 70          # V24's `text_plate` clearance over the racers
HOOK_LINES = ("PICK A", "COLOR")


def _ink(plate, floor: int = 200):
    """The bounding box of everything solid in a plate, shadow excluded."""
    alpha = plate.getchannel("A").point(lambda value: 255 if value >= floor else 0)
    box = alpha.getbbox()
    if box is None:
        raise ValueError("the mark drew nothing")
    return box


def _line_ink_width(text: str, size: int) -> int:
    plate = overlays._shadowed(text, size, DELIVERY[1] // 2, tracking=0.09)
    box = _ink(plate)
    return box[2] - box[0]


def hook_size(
    lines: Sequence[str] = HOOK_LINES,
    gutter: float = HOOK_GUTTER,
    cap: int = 400,
) -> int:
    """The largest size whose widest line keeps `gutter` clear of both edges.

    Fitted against the **rendered ink** rather than against a metric sum, so a
    font substitution moves the type instead of pushing it off the frame. A
    TrueType advance is linear in the size, so one measurement gives the curve
    and there is nothing to search; it is then walked down by ones to absorb
    hinting, which is not linear.
    """
    target = DELIVERY[0] * (1.0 - 2.0 * gutter)
    reference = 100
    natural = max(_line_ink_width(text, reference) for text in lines)
    size = max(24, min(cap, int(target / natural * reference)))
    while size > 24 and max(_line_ink_width(text, size) for text in lines) > target:
        size -= 1
    return size


def hook_plate(
    lines: Sequence[str] = HOOK_LINES,
    size: int | None = None,
    top_baseline: int | None = None,
    lead: float = HOOK_LEAD,
):
    """The opening mark, drawn through `overlays._shadowed` and nothing else."""
    from PIL import Image

    size = hook_size(lines) if size is None else size
    if top_baseline is None:
        top_baseline = overlays.PICK_ONE_BASELINE
    plate = Image.new("RGBA", DELIVERY, (0, 0, 0, 0))
    for index, text in enumerate(lines):
        baseline = int(round(top_baseline + index * lead * size))
        plate.alpha_composite(
            overlays._shadowed(text, size, baseline, tracking=0.09)
        )
    return plate


def hook_placement(
    replay: dict[str, Any],
    track: dict[str, Any],
    clock: Clock,
    lines: Sequence[str] = HOOK_LINES,
    marbles: int = 8,
) -> dict[str, Any]:
    """Where the mark goes, from where the racers are on this film's own frames.

    The block is centred in the band between `HOOK_TOP` and the topmost racer
    pixel over the mark's whole life, less `HOOK_CLEARANCE`. The one thing the
    mark may never do is cover the eight things it is pointing at, so that band
    is a hard constraint and the report carries the clearance it achieved.
    """
    from sloped import presentation as pres

    top, bottom = float(DELIVERY[1]), 0.0
    for marble in range(marbles):
        for _when, x, y, radius in pres.screen_track(
            replay, track, clock, marble, (HOOK_IN, HOOK_OUT_TO)
        ):
            if -200.0 < x < DELIVERY[0] + 200.0:
                top = min(top, y - radius)
                bottom = max(bottom, y + radius)

    size = hook_size(lines)
    probe = overlays._shadowed(lines[0], size, 1000, tracking=0.09)
    box = _ink(probe)
    cap = box[3] - box[1]
    block = cap + (len(lines) - 1) * HOOK_LEAD * size
    floor = top - HOOK_CLEARANCE
    room = floor - HOOK_TOP
    top_baseline = int(round(HOOK_TOP + max(0.0, (room - block)) * 0.5 + cap))
    ink_low = top_baseline + (len(lines) - 1) * HOOK_LEAD * size

    return {
        "text": HOOK_TEXT,
        "lines": list(lines),
        "size": size,
        "lead": HOOK_LEAD,
        "top_baseline": top_baseline,
        "cap_px": int(cap),
        "cap_px_at_270": round(cap / 4.0, 2),
        "line_ink_px": [int(_line_ink_width(text, size)) for text in lines],
        "gutter_px": int(round(DELIVERY[0] * HOOK_GUTTER)),
        "block_px": int(round(block)),
        "racers_top": round(top, 1),
        "racers_bottom": round(bottom, 1),
        "clearance": round(top - ink_low, 1),
        "band": [HOOK_TOP, int(round(floor))],
        "in": HOOK_IN,
        "out_from": HOOK_OUT_FROM,
        "out_to": HOOK_OUT_TO,
    }


# --- the winner's ring ------------------------------------------------------

# **On the crossing, not after it.** V22.1 opened its ring 0.200 s late and V24's
# payoff lab measured that this put one frame of it on a visible marble; V31's
# preview inherited 0.180. On this film the winner is on screen continuously
# from 0.58 s before the line to the last frame - `ring_track` measures it - so
# the mark opens on the frame the marble crosses and Part C's "through the
# crossing" is literal.
RING_DELAY = 0.0
# `overlays.winner_ring`'s envelope is designed for this length: the glow is in
# the first half, the flash in the first ninth and the ring's sine fade spans
# the whole of it. Shorter reads as a blink.
RING_SECONDS = 0.70


def ring_track(
    replay: dict[str, Any],
    track: dict[str, Any],
    clock: Clock,
    spine: Any,
    marble: int,
    crossing: float,
    delay: float = RING_DELAY,
    seconds: float = RING_SECONDS,
) -> dict[str, Any]:
    """Where the ring is on every frame of its life, and whether it is on a ball.

    Two independent occlusion tests, because each catches what the other cannot:

    * `spine.blocked` - the course's own geometry between the lens and the
      marble, which is the test `race2.readability` uses;
    * the frame itself - how much of the projected disc carries the racer's own
      hue, which is the test V24's payoff lab used, and the only one that can
      see a *competitor* in the way.

    The tool refuses to composite on a geometric block. A competitor crossing in
    front is a race event, not a fault, so it is reported and not refused.
    """
    from sloped import presentation as pres

    start = round((crossing + delay) * clock.fps) / clock.fps
    stop = start + seconds
    rows = [
        row for row in pres.screen_track(replay, track, clock, marble, (start, stop))
        if int(round(row[0] * clock.fps)) <= clock.master_frames - 1
    ]
    if not rows:
        raise ValueError("the winner is not on any frame of the ring's window")

    out: list[dict[str, Any]] = []
    blocked_frames = 0
    for when, x, y, radius in rows:
        camera = _camera_position(track, when)
        point = _marble_point(replay, when, marble)
        blocked = bool(spine.blocked(camera, point)) if point is not None else True
        inside = (
            radius < x < DELIVERY[0] - radius
            and radius < y < DELIVERY[1] - radius
        )
        if blocked or not inside:
            blocked_frames += 1
        out.append(
            {
                "t": round(when, 4),
                "frame": int(round(when * clock.fps)),
                "x": round(x, 1),
                "y": round(y, 1),
                "r": round(radius, 1),
                "blocked": blocked,
                "inside": bool(inside),
            }
        )
    # **Whole frames, carried as integers.** The offset the filter graph gets is
    # `from_frame / fps`, not a rounded number of seconds. `sloped_short` records
    # why: an ffmpeg `setpts` offset that is not a whole tick lands the sequence
    # between two frames and the first one is never composited - and the first
    # one is the flash, the only part of the mark synchronised to the crossing.
    # Writing `round(start, 4)` into the report and reading it back was enough to
    # re-introduce exactly that; the delivered file was measured against the
    # delivered master and the crossing frame differed from it by 0.9 of 255,
    # which is encoder noise and not a mark.
    return {
        "marble": marble,
        "crossing": round(crossing, 4),
        "from": round(start, 4),
        "to": round(round(out[-1]["t"], 4), 4),
        "from_frame": int(round(start * clock.fps)),
        "to_frame": int(out[-1]["frame"]),
        "seconds": seconds,
        "frames": len(out),
        "frames_blocked": blocked_frames,
        "radius_px": [
            round(min(row["r"] for row in out), 1),
            round(max(row["r"] for row in out), 1),
        ],
        "track": out,
    }


def _camera_position(track: dict[str, Any], when: float) -> tuple[float, float, float]:
    from sloped import presentation as pres

    camera, _aim, _fov = pres._camera_at(track, when)
    return camera


def _marble_point(
    replay: dict[str, Any], when: float, marble: int
) -> tuple[float, float, float] | None:
    """One marble's layout-unit position on the replay frame nearest `when`."""
    scale = float(replay.get("units", {}).get("render_scale", 0.57))
    best = min(replay["frames"], key=lambda frame: abs(float(frame["t"]) - when))
    sample = next(
        (one for one in best["marbles"] if int(one["id"]) == marble), None
    )
    if sample is None:
        return None
    return tuple(float(value) * scale for value in sample["p"])


# --- the payoff card --------------------------------------------------------

# V24's recognition beat, the middle of the 0.8-1.5 s band its lab measured. The
# card then holds to the last frame: this film has no tail behind the card to
# protect, and the last thing on screen in a Short is the thing a viewer reads
# while deciding whether to say a colour.
CARD_BEAT = 1.0
CARD_STYLE = "plate"
# The luma a row may reach across the text corridor and still be a plate for
# warm-white letters. V24's own figure, measured the same way.
CARD_LUMA = 130.0
CARD_CORRIDOR = (96, 984)


def card_band(
    frames_dir: str,
    replay: dict[str, Any],
    track: dict[str, Any],
    clock: Clock,
    start: float,
    marbles: int = 8,
    luma: float = CARD_LUMA,
) -> dict[str, Any]:
    """The tallest band of rows the card may sit in, over its whole life.

    Two conditions, both measured on the delivered frames of *this* film:

    * no row may exceed `luma` anywhere across the text corridor, on any frame
      the card is up - the maximum, not the mean, because a card on a chequer
      lands half its glyphs on the dark tile and half on the light one;
    * no row may carry a racer that has not finished yet. A marble parked on the
      deck is scenery; a marble still coming down the channel is the race, and
      the brief's "do not obscure the final race" is about that one.
    """
    import numpy as np
    from PIL import Image
    from sloped import presentation as pres

    finished = {
        int(event["id"]): float(event["t"])
        for event in replay.get("events", ())
        if event["kind"] == "finish_line"
    }
    racing = np.zeros(DELIVERY[1], dtype=bool)
    for marble in range(marbles):
        for when, x, y, radius in pres.screen_track(
            replay, track, clock, marble, (start, clock.segments[-1][1])
        ):
            if when > finished.get(marble, math.inf) + 1e-9:
                continue
            if -200.0 < x < DELIVERY[0] + 200.0:
                low = max(0, int(y - radius - 6))
                high = min(DELIVERY[1], int(y + radius + 6))
                racing[low:high] = True

    brightest = None
    counted = 0
    for index in range(int(round(start * clock.fps)), clock.master_frames, 2):
        path = os.path.join(frames_dir, f"frame_{index:06d}.png")
        if not os.path.isfile(path):
            continue
        pixels = np.asarray(Image.open(path).convert("RGB")).astype(float)
        light = (
            0.2126 * pixels[..., 0]
            + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2]
        )
        row_max = light[:, CARD_CORRIDOR[0]:CARD_CORRIDOR[1]].max(1)
        brightest = row_max if brightest is None else np.maximum(brightest, row_max)
        counted += 1
    if brightest is None:
        raise ValueError(f"no frames under {frames_dir} for the card's window")

    usable = (brightest <= luma) & (~racing)
    best = (0, 0)
    run_start = None
    for index in range(DELIVERY[1] + 1):
        inside = index < DELIVERY[1] and bool(usable[index])
        if inside and run_start is None:
            run_start = index
        elif not inside and run_start is not None:
            if index - run_start > best[1] - best[0]:
                best = (run_start, index)
            run_start = None
    if best[1] - best[0] < 40:
        raise ValueError("no band on this film is dark enough and clear of the race")
    return {
        "band": [int(best[0]), int(best[1])],
        "height": int(best[1] - best[0]),
        "max_luma": round(float(brightest[best[0]:best[1]].max()), 1),
        "frames_measured": counted,
        "from": round(start, 4),
        "racing_rows": _row_runs(racing),
    }


def _row_runs(mask) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = None
    for index, value in enumerate(mask):
        if value and start is None:
            start = index
        elif not value and start is not None:
            out.append((start, index))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def card_plate(winner: int, from_place: int, band: Sequence[int], style: str = CARD_STYLE):
    """The payoff card, built by `v24_payoff` and translated into this band.

    **Built, not rebuilt.** `v24_payoff.build` lays two lines out inside its own
    `PAYOFF_BAND` by measurement - the type is fitted to the gutter, the lozenge
    is the racer's exact hue, the fact line is capped below the headline - and
    all of that is correct here. The one thing that is not is *where*: its band
    was measured on Race #1's finish lens. This film's band is the same height
    to within a pixel, so the card is translated rather than re-laid-out, which
    keeps the drawing identical to the one the payoff lab measured.

    **It is aligned to the band's floor, not its ceiling.** The floor is where
    the race is - `card_band` put it exactly one row above the highest pixel any
    still-racing marble reaches - and the ceiling is where a phone's own
    furniture is. Measured on this film, sliding the card down to the floor is
    worth 50 px of top margin and costs nothing: 25 px higher and the card
    starts crossing arriving racers, which is the defect V24's payoff lab found
    in the shipped Race #1 card.
    """
    from PIL import Image

    payoff = v24_payoff.build(style=style, winner=winner, from_place=from_place)
    shift = float(band[1] - _ink(payoff.image)[3])
    image = payoff.image
    if abs(shift) >= 0.5:
        image = image.transform(
            image.size, Image.AFFINE, (1, 0, 0, 0, 1, -shift),
            resample=Image.BILINEAR,
        )
    box = _ink(image)
    return payoff, image, {
        "style": style,
        "label": payoff.label,
        "winner": winner,
        "from_place": from_place,
        "hue": list(overlays.MARBLE_HUES[winner % len(overlays.MARBLE_HUES)]),
        "shift": round(shift, 1),
        "band": [int(band[0]), int(band[1])],
        "ink_box": [int(value) for value in box],
        "inside_band": bool(box[1] >= band[0] and box[3] <= band[1]),
        "text_contrast": round(payoff.text_contrast, 2),
        "colour_pixels": int(payoff.colour_pixels),
    }

"""Check that a rendered race sequence shows the race the replay describes.

The determinism tools that already exist answer a different question.
`compare_frames.py` says whether two renders of one replay are the same
images, which catches a renderer that is not reproducible but not one that is
reproducibly wrong. This says whether the pictures are of the *race*: it takes
the position the replay recorded for each racer, works out which pixels that
racer should occupy, and looks.

It can do that because the race camera is orthographic and points straight
down. One simulation pixel is one frame pixel, everywhere in the frame, so the
mapping is two subtractions::

    frame_x = racer_x
    frame_y = racer_y - camera_y

with `camera_y` read from the same frame of the replay. There is no projection
to invert and no perspective to allow for, which is most of the reason the
race camera is built that way at this stage - a check that had to model a 78
degree perspective camera would be testing its own arithmetic as much as the
renderer's.

    python tools/verify_race_render.py output/race_v02/render_split_1000
    python tools/verify_race_render.py RENDER_DIR --replay REPLAY.json --frames 24

A racer is found by collecting every nearby pixel whose colour points the same
way as that racer's, and then measuring the box those pixels fill. Direction
rather than value because the renderer draws a lit sphere: diffuse lighting
scales a colour without rotating it, so the hue survives the shading that the
raw RGB does not.

The box, rather than the average of those pixels, because the light comes from
one side - so the *lit part* of a ball is offset from the ball even when the
ball is exactly where it should be, and its centroid is offset with it. Where
the matched pixels stop is not: a sphere's silhouette is symmetric whichever
side of it is lit. That makes the box's centre the position check and the
box's size a second, weaker check that the thing measured is a racer-sized
object rather than a stray highlight.

Three things put a few pixels of noise into that measurement, and all three
are properties of the picture rather than faults in it:

* the renderer bleeds a glow around a lit ball, in exactly the racer's hue, so
  the silhouette can measure larger than the racer;
* a racer resting against a wall or behind another racer has part of itself
  hidden, so it measures smaller and its box shifts away from what is covered;
* one racer is silver, whose hue is not far from the course chrome's.

So the tolerance here is set to catch a *placement* bug - a wrong camera
offset, a mirrored axis, a forgotten half-frame - all of which are out by
hundreds of pixels, not by five. What the check reports is the whole
distribution, so a drift of a few pixels would be visible as a change in the
mean rather than hidden behind a pass.

Racers underneath the overlay are skipped rather than measured. The HUD is
drawn on top of the race by design, and a ball behind the timer panel is not
a rendering fault.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rendering import png_frames  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAMES_SUBDIR,
    METADATA_NAME,
    MODE_RACE,
    frame_filename,
)

# What counts as a placement failure, in pixels. Generous against the accuracy
# the renderer actually achieves - the measured mean is one and a half pixels
# and the median is under one - because the measurement carries several pixels
# of its own noise and a real bug is out by hundreds.
#
# Sixteen rather than ten because of one measurable worst case: the silver
# racer, resting against a slate wall, in the pile of finished racers in the
# paddock. Its hue is the closest of the ten to the course chrome and most of
# it is behind other racers, so the box that can be measured is a fragment of
# a ball with a wall on one side of it. That reads at thirteen pixels out on
# a course where every other measurement is under three.
POSITION_TOLERANCE = 16.0

# The measured silhouette against the racer's diameter, as a ratio. Wide on
# purpose: glow inflates it and occlusion shrinks it. It is here to catch a
# racer drawn at the wrong scale, which would be out by a factor, not by a
# fifth.
SIZE_RATIO_MIN = 0.55
SIZE_RATIO_MAX = 1.75

# How far from the expected centre to look, in pixels. Comfortably more than a
# racer radius, so a ball slightly out of place is still measured whole.
SEARCH_RADIUS = 46

# How closely a pixel's colour has to point the same way as the racer's, as
# the cosine of the angle between the two RGB directions.
COLOR_COSINE = 0.995

# How bright a pixel has to be, as a fraction of the racer's own brightest
# channel, to count as part of that racer. This is what holds most of the glow
# out: the halo is the racer's hue exactly, so no colour test can reject it,
# but it is much dimmer than the ball. It rejects the course chrome too, which
# is dark by design.
MIN_LEVEL_FRACTION = 0.5

# How saturated a pixel has to be, as a fraction of the racer's own
# saturation. Relative rather than fixed because the field includes a silver
# racer at 0.12 saturation: a fixed floor high enough to reject grey chrome
# would reject the silver racer as well, and one low enough to keep it would
# match everything.
MIN_SATURATION_FRACTION = 0.6

# Below this many matching pixels there is not enough of a ball to measure -
# one mostly behind a wall, or a sliver at the edge of the search window.
MIN_PIXELS = 40

# Where the overlay covers the race, in frame pixels, as (x, y, width, height).
# Taken from `race_hud.gd`; a racer whose centre falls inside one of these is
# behind the HUD and is not looked for.
HUD_RECTS = (
    (425, 24, 230, 76),      # the clock
    (42, 116, 380, 190),     # the standings
    (112, 1560, 856, 190),   # the result panel
)
# The countdown numeral, which covers a third of the frame - but only while
# there is a countdown. Excluding it for the whole race would throw away most
# of the measurements in the busiest part of the frame.
COUNTDOWN_RECT = (380, 700, 320, 320)


class VerifyError(RuntimeError):
    """The rendered sequence cannot be checked against the replay."""


def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        raise VerifyError(f"no file at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_replay(render_dir: str, explicit: str | None) -> str:
    """The replay a render was made from, from the sidecar if not given."""
    if explicit:
        return explicit
    metadata = load_json(os.path.join(render_dir, METADATA_NAME))
    section = metadata.get("replay") or {}
    mode = str(section.get("mode", "battle"))
    if mode != MODE_RACE:
        raise VerifyError(
            f"{render_dir} is a {mode} render; this tool only checks races"
        )
    name = str(section.get("path") or section.get("name") or "")
    if not name:
        raise VerifyError(f"{render_dir}: the sidecar does not name a replay")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(root, name)
    return candidate if os.path.isfile(candidate) else name


def _saturation(color) -> float:
    peak = max(color)
    return 0.0 if peak <= 0 else (peak - min(color)) / peak


def _direction(color) -> tuple[float, float, float]:
    length = math.sqrt(sum(float(channel) ** 2 for channel in color))
    if length <= 0.0:
        return (0.0, 0.0, 0.0)
    return tuple(float(channel) / length for channel in color)


def locate(
    pixels: bytes,
    width: int,
    height: int,
    center: tuple[float, float],
    color: tuple[int, int, int],
) -> tuple[tuple[float, float], tuple[float, float], int]:
    """Where a racer's colour actually is, as a box, and how big that box is.

    Returns the box centre, its width and height, and how many pixels went
    into it. A count of zero means no pixel of that colour is anywhere near
    where the replay said the racer would be.
    """
    wanted = _direction(color)
    level_floor = max(color) * MIN_LEVEL_FRACTION
    saturation_floor = _saturation(color) * MIN_SATURATION_FRACTION
    target_x, target_y = int(round(center[0])), int(round(center[1]))
    left = max(0, target_x - SEARCH_RADIUS)
    right = min(width - 1, target_x + SEARCH_RADIUS)
    top = max(0, target_y - SEARCH_RADIUS)
    bottom = min(height - 1, target_y + SEARCH_RADIUS)

    min_x, max_x = width, -1
    min_y, max_y = height, -1
    matched = 0
    for y in range(top, bottom + 1):
        row = y * width * 3
        for x in range(left, right + 1):
            offset = row + x * 3
            red, green, blue = pixels[offset], pixels[offset + 1], pixels[offset + 2]
            peak = max(red, green, blue)
            if peak < level_floor:
                continue
            if (peak - min(red, green, blue)) / peak < saturation_floor:
                continue
            found = _direction((red, green, blue))
            if sum(a * b for a, b in zip(found, wanted)) < COLOR_COSINE:
                continue
            matched += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)

    if matched < MIN_PIXELS:
        return (0.0, 0.0), (0.0, 0.0), matched
    return (
        ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0),
        (float(max_x - min_x + 1), float(max_y - min_y + 1)),
        matched,
    )


def behind_hud(center: tuple[float, float], race_time: float) -> bool:
    """Whether the overlay is drawn over this point of the frame.

    `race_time` is negative during the countdown, which is the only time the
    numeral is on screen.
    """
    x, y = center
    rects = HUD_RECTS if race_time >= 0.0 else HUD_RECTS + (COUNTDOWN_RECT,)
    for left, top, width, height in rects:
        if left <= x <= left + width and top <= y <= top + height:
            return True
    return False


def frame_indices(replay: dict, count: int) -> list[int]:
    """Evenly spaced gameplay frames, always including the first and last.

    Spread rather than sampled at random: a race changes character as it goes
    - a grid, then a scramble, then a finish - and a check that only ever
    looked at the middle would miss a camera that was wrong at the start.
    """
    total = len(replay.get("frames", []))
    if total < 1:
        raise VerifyError("replay has no frames")
    if count >= total:
        return list(range(total))
    step = (total - 1) / (count - 1) if count > 1 else 1
    return sorted({int(round(index * step)) for index in range(count)})


def verify(render_dir: str, replay: dict, count: int) -> list[str]:
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    if not os.path.isdir(frames_dir):
        raise VerifyError(f"no frames directory in {render_dir}")

    meta = {int(entry["id"]): entry for entry in replay.get("racers", [])}
    frames = replay["frames"]
    indices = frame_indices(replay, count)
    problems: list[str] = []
    offsets: list[float] = []
    ratios: list[float] = []
    checked = missing = hidden = 0

    for index in indices:
        path = os.path.join(frames_dir, frame_filename(index))
        if not os.path.isfile(path):
            problems.append(f"{frame_filename(index)} is not there")
            continue
        width, height, pixels = png_frames.rgb_bytes(path)
        frame = frames[index]
        camera_y = float(frame.get("camera_y", 0.0))

        for racer in frame.get("racers", []):
            if bool(racer.get("retired", False)):
                continue
            racer_id = int(racer["id"])
            center = (float(racer["x"]), float(racer["y"]) - camera_y)
            # Only racers the frame actually contains can be looked for. One
            # off the bottom of a portrait frame is not a rendering fault, it
            # is a racer the camera has left behind. The margin keeps a ball
            # that is half out of frame from being measured as a small one.
            if not (SEARCH_RADIUS <= center[1] <= height - SEARCH_RADIUS):
                continue
            if not (SEARCH_RADIUS <= center[0] <= width - SEARCH_RADIUS):
                continue
            if behind_hud(center, float(frame.get("race_time", 0.0))):
                hidden += 1
                continue

            checked += 1
            entry = meta[racer_id]
            color = tuple(int(value) for value in entry["color"])
            diameter = 2.0 * float(entry["radius"])
            found, size, matched = locate(pixels, width, height, center, color)
            if matched < MIN_PIXELS:
                missing += 1
                problems.append(
                    f"{frame_filename(index)}: racer {racer_id} expected at"
                    f" ({center[0]:.0f}, {center[1]:.0f}); only {matched} pixels"
                    f" of its colour {color} are near there"
                )
                continue

            offset = math.dist(found, center)
            offsets.append(offset)
            if offset > POSITION_TOLERANCE:
                problems.append(
                    f"{frame_filename(index)}: racer {racer_id} is centred at"
                    f" ({found[0]:.1f}, {found[1]:.1f}), replay says"
                    f" ({center[0]:.1f}, {center[1]:.1f}) - {offset:.1f}px out"
                )

            ratio = max(size) / diameter
            ratios.append(ratio)
            if not (SIZE_RATIO_MIN <= ratio <= SIZE_RATIO_MAX):
                problems.append(
                    f"{frame_filename(index)}: racer {racer_id} measures"
                    f" {max(size):.0f}px across, replay says {diameter:.0f}px"
                )

    if not checked:
        problems.append("no racer was inside any sampled frame")
        return problems

    print(
        f"    {len(indices)} frames sampled,"
        f" {checked} racer positions measured, {hidden} behind the HUD\n"
        f"    located {checked - missing}, missing {missing}\n"
        f"    position error: mean {_mean(offsets):.2f}px,"
        f" median {_percentile(offsets, 0.5):.2f}px,"
        f" 95th {_percentile(offsets, 0.95):.2f}px,"
        f" worst {_worst(offsets):.2f}px  (fails above {POSITION_TOLERANCE:.0f}px)\n"
        f"    silhouette vs replay diameter: mean {_mean(ratios):.2f}x,"
        f" range {min(ratios, default=0.0):.2f}-{max(ratios, default=0.0):.2f}x"
    )
    return problems


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("inf")
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("inf")


def _worst(values: list[float]) -> float:
    return max(values) if values else float("inf")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="check a rendered race against the replay it came from"
    )
    parser.add_argument("render", help="a render directory")
    parser.add_argument("--replay", default=None, help="the replay, if not in metadata")
    parser.add_argument(
        "--frames", type=int, default=12, help="how many frames to sample"
    )
    args = parser.parse_args()

    try:
        replay_path = resolve_replay(args.render, args.replay)
        replay = load_json(replay_path)
        print(f"=== {args.render} ===\n    replay {replay_path}")
        problems = verify(args.render, replay, max(2, args.frames))
    except (VerifyError, png_frames.PngError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if problems:
        print(f"\n{len(problems)} problem(s):", file=sys.stderr)
        for problem in problems[:20]:
            print(f"  {problem}", file=sys.stderr)
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more", file=sys.stderr)
        return 1

    print("    OK: every sampled racer is where the replay put it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

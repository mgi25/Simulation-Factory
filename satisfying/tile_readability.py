"""Measuring what a viewer can actually see, instead of asking whether it looks good.

Phase 3 is a readability experiment, and readability arguments rot fast when
they are made by eye: a renderer author looking at a 1080x1920 PNG on a 27-inch
monitor is not looking at what a viewer sees. This module answers the brief's
questions as numbers, and it answers them from two independent directions so a
disagreement between them is visible.

**Predicted, from the playback document.** The camera is orthographic with
`keep_aspect = KEEP_WIDTH`, so world-to-pixel is exactly
`frame_width / camera_size` and `camera_size = 2*circumradius /
ARENA_WIDTH_FRACTION`. Every geometric question - how many pixels across is the
ball, how long is a tile on screen, how far does the ball travel between two
frames at 30 fps - therefore has a closed-form answer that needs no render at
all. `frame_geometry` and `motion_report` are that arithmetic.

**Measured, from the rendered PNG.** Whether an activated tile really is
brighter than an inactive one is a fact about the renderer's materials, lights
and glow, and no amount of arithmetic will produce it. `still_report` reads the
image back and samples the pixels where the tiles are.

## Ball readability, and the strobing question Phase 1 left open

Phase 1 warned that its diagnostic renderer's trail strobed at higher speeds
and did not characterise it. Here is the characterisation, and it is not a
matter of taste:

At 85 wu/s in a circumradius-10 arena rendered 0.86 of a 1080-pixel frame wide,
the scale is 46.5 px/wu. The ball's collision diameter is 0.9 wu = 41.8 px. In
one frame at 30 fps the ball travels 2.833 wu = **132 px**, which is 3.2 ball
diameters; at 60 fps it travels 66 px, 1.6 diameters. In both cases consecutive
frames show the ball at positions that **do not overlap**, and a sequence of
non-overlapping discs is exactly what "strobing" means. It is not a defect of
Phase 1's renderer and no ball size fixes it: a ball wide enough to overlap at
30 fps would be 132 px across, a third of the arena.

So the treatment has to be temporal, and `travel_px` against `ball_diameter_px`
is the number that says whether a given trail length closes the gap.
`frames_over_ball_diameter` counts the frames where it would not, and
`trail_covers_frame_step` answers the only question that matters about a trail:
is the streak it draws at least as long as the distance the ball moves between
two frames? If it is, consecutive frames overlap and the motion is continuous.

## What `still_report` samples, and why not the whole image

A tile occupies a known quadrilateral in the frame - the renderer put it there
from the playback document's own geometry, and this module projects the same
numbers. So instead of thresholding the image or finding blobs, it samples a
small disc at each tile's projected midpoint and takes the median. Median
rather than mean because the chamfer rims are deliberately shaded differently
from the tile face and a mean would average the face with its own bevel.

The separation reported is between the *populations*: the median luminance of
all inactive tiles against the median of all activated ones, plus the worst
case - the brightest inactive tile against the dimmest activated one. The worst
case is the one that decides whether a viewer at 50/51 can find the last dark
tile, because they are not comparing medians, they are looking for one tile.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Sequence

from satisfying import tile_playback

__all__ = [
    "ARENA_WIDTH_FRACTION",
    "ARENA_CENTRE_OFFSET_FRACTION",
    "BALL_DRAW_SCALE",
    "TRAIL_SECONDS",
    "TILE_GAP_FRACTION",
    "TILE_RADIAL_THICKNESS",
    "SAFE_MARGIN_FRACTION",
    "HOOK_TOP_FRACTION",
    "COUNTER_TOP_FRACTION",
    "project",
    "frame_geometry",
    "motion_report",
    "still_report",
    "strobe_report",
    "compare_audit",
    "luminance",
]

# These mirror `godot/scripts/tile_escape_scene.gd`. They are duplicated rather
# than imported because GDScript constants cannot be imported into Python, and
# `test_tile_escape_phase3.py` parses the GDScript and asserts the two copies
# agree - which is a stronger guarantee than a shared file nobody checks.
# Phase 6. Was 0.86 through Phases 3-5, which was chosen against the frame and
# not against the player. Measured in `tile_safe_area`, a 0.86-wide centred
# arena puts nine of its fifty-one tiles under YouTube's action rail, and on
# seed 3530 one of those - tile 11 - is the forty-ninth tile to activate, so
# during the 48/51 window one of the three remaining dark tiles is behind an
# icon. 0.765 with the offset below is the widest composition that clears every
# tile on all five pacing-valid seeds. It costs 11% of scale: the ball goes
# from 60.6 to 53.9 drawn pixels and a tile from 48.4 to 43.0, and every
# Phase 3 motion verdict is unchanged because the trail and the frame step
# scale together - `trail_covers_frame_step` holds at 2.70x either way.
ARENA_WIDTH_FRACTION = 0.765
# How far left of centre the arena sits, as a fraction of the frame width.
# The rail is on the right and only on the right, so the cheapest way to clear
# it is to stop pretending the frame is symmetric. A pure shrink would have had
# to reach 0.68 to clear the same rail centred, which costs 21% of scale
# instead of 11%; the offset buys back half the loss. Negative is left.
ARENA_CENTRE_OFFSET_FRACTION = -0.060
BALL_DRAW_SCALE = 1.45
TRAIL_SECONDS = 0.09
TRAIL_SAMPLES = 34
SAFE_MARGIN_FRACTION = 0.05
HOOK_TOP_FRACTION = 0.075
# Phase 6. Was 0.815, which put the counter's glyphs at 0.836-0.878 of the
# frame - measured on a real frame, not predicted - and YouTube's title and
# @handle block starts at 0.84. Over half of "X / 51" was underneath it on the
# measured model and all of it on the strict one. The counter is the only
# element carrying the premise, so it moves up until it clears every model.
COUNTER_TOP_FRACTION = 0.745
TILE_GAP_FRACTION = 0.075
# The tile slab's depth in world units, outward from the collision segment.
# Mirrored here in Phase 6 so `tile_safe_area` can build a tile's drawn face
# rather than its collision line - what the player's UI can cover is what is
# drawn, and a tile is a quadrilateral on screen, not a segment.
TILE_RADIAL_THICKNESS = 0.62

# How big the largest luminance jump between two tiles has to be before the
# frame is treated as holding two populations rather than one. Thirty levels
# out of 255: far above the within-population spread the chamfer shading
# produces (about 10), far below the 80-180 level gap a real inactive/activated
# boundary shows.
SEPARATION_MIN_GAP = 30.0
# When there is only one population, this decides which one it is.
SINGLE_POPULATION_LIT = 120.0


def luminance(rgb: Sequence[float]) -> float:
    """Rec. 709 relative luminance, 0-255. What "brighter" means here."""
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def pixels_per_unit(document: dict[str, Any], width: int) -> float:
    """The exact scale the orthographic camera produces at this frame width."""
    circumradius = float(document["arena"]["circumradius"])
    camera_size = (2.0 * circumradius) / ARENA_WIDTH_FRACTION
    return width / camera_size


def project(
    document: dict[str, Any], point: Sequence[float], width: int, height: int
) -> tuple[float, float]:
    """A simulation point in pixels. Exact: the camera is orthographic.

    Still a pure scale plus a translation, which is what keeps every distance
    measurement in this module valid after Phase 6 moved the arena off centre:
    the offset cancels in any difference of two projected points.
    """
    scale = pixels_per_unit(document, width)
    return (width * 0.5 + ARENA_CENTRE_OFFSET_FRACTION * width
            + point[0] * scale,
            height * 0.5 - point[1] * scale)


def frame_geometry(
    document: dict[str, Any], width: int, height: int
) -> dict[str, Any]:
    """Composition and apparent size, in pixels, without rendering anything."""
    arena = document["arena"]
    scale = pixels_per_unit(document, width)
    circumradius = float(arena["circumradius"])
    ball_radius = float(document["config"]["ball_radius"])

    arena_width_px = 2.0 * circumradius * scale
    # A regular 17-gon's height is circumradius + apothem: a flat side at the
    # bottom and a vertex at the top, so it is not as tall as it is wide.
    arena_height_px = (circumradius + float(arena["apothem"])) * scale
    top_px = height * 0.5 - circumradius * scale
    bottom_px = height * 0.5 + float(arena["apothem"]) * scale

    hook_top = height * HOOK_TOP_FRACTION
    hook_height = height * 0.0305 * 2.2
    counter_top = height * COUNTER_TOP_FRACTION

    return {
        "frame": [width, height],
        "pixels_per_unit": scale,
        "arena_width_px": arena_width_px,
        "arena_height_px": arena_height_px,
        "arena_occupancy_width": arena_width_px / width,
        "arena_occupancy_height": arena_height_px / height,
        "arena_occupancy_area": (
            # A regular n-gon of circumradius R has area
            # 0.5 * n * R^2 * sin(2*pi/n).
            0.5
            * int(arena["sides"])
            * (circumradius * scale) ** 2
            * math.sin(2.0 * math.pi / int(arena["sides"]))
        )
        / (width * height),
        "tile_length_px": float(arena["tile_length"]) * scale,
        "tile_drawn_length_px": (
            float(arena["tile_length"]) * (1.0 - 2.0 * TILE_GAP_FRACTION) * scale
        ),
        "ball_diameter_px": 2.0 * ball_radius * scale,
        "ball_drawn_diameter_px": 2.0 * ball_radius * BALL_DRAW_SCALE * scale,
        "arena_centre_px": width * 0.5 + ARENA_CENTRE_OFFSET_FRACTION * width,
        "arena_left_px": (width * 0.5 + ARENA_CENTRE_OFFSET_FRACTION * width
                          - 0.5 * arena_width_px),
        "arena_right_px": (width * 0.5 + ARENA_CENTRE_OFFSET_FRACTION * width
                           + 0.5 * arena_width_px),
        "arena_top_px": top_px,
        "arena_bottom_px": bottom_px,
        "hook_top_px": hook_top,
        "hook_bottom_px": hook_top + hook_height,
        "hook_clearance_px": top_px - (hook_top + hook_height),
        "counter_top_px": counter_top,
        "counter_clearance_px": counter_top - bottom_px,
        "safe_margin_px": width * SAFE_MARGIN_FRACTION,
        "arena_side_margin_px": (width - arena_width_px) * 0.5,
    }


def motion_report(
    document: dict[str, Any], fps: float, width: int, height: int
) -> dict[str, Any]:
    """How far the ball moves between rendered frames, and whether that reads.

    Walks every frame of the run at `fps` and measures the pixel distance from
    the previous frame's ball position - along the straight line between them,
    which is what the eye has to bridge. A step larger than the drawn ball
    diameter means two consecutive frames show the ball at non-overlapping
    positions, which is the definition of a strobe.
    """
    scale = pixels_per_unit(document, width)
    end = float(document["completion_seconds"] or document["end_seconds"])
    frames = max(2, int(math.floor(end * fps)) + 1)
    ball_px = 2.0 * float(document["config"]["ball_radius"]) * scale
    drawn_px = ball_px * BALL_DRAW_SCALE

    travels: list[float] = []
    previous = tile_playback.position_at(document, 0.0)
    for index in range(1, frames):
        here = tile_playback.position_at(document, index / fps)
        travels.append(math.dist(previous, here) * scale)
        previous = here

    travels_sorted = sorted(travels)
    median = travels_sorted[len(travels_sorted) // 2]
    # The trail is a time window, so the streak it draws is as long as the ball
    # travels in `TRAIL_SECONDS`. If that is at least the frame step, the
    # streak drawn on frame n reaches back to where the ball was on frame n-1
    # and the motion is continuous rather than a sequence of dots.
    trail_px = float(document["config"]["speed"]) * TRAIL_SECONDS * scale
    return {
        "fps": fps,
        "frames": frames,
        "ball_diameter_px": ball_px,
        "ball_drawn_diameter_px": drawn_px,
        "travel_px_median": median,
        "travel_px_max": max(travels),
        "travel_px_mean": sum(travels) / len(travels),
        "travel_in_ball_diameters_median": median / ball_px,
        "frames_over_ball_diameter": sum(1 for t in travels if t > drawn_px),
        "frames_over_ball_diameter_fraction": (
            sum(1 for t in travels if t > drawn_px) / len(travels)
        ),
        "trail_length_px": trail_px,
        "trail_samples": TRAIL_SAMPLES,
        "trail_sample_spacing_px": trail_px / TRAIL_SAMPLES,
        "trail_sample_spacing_in_ball_radii": (
            (trail_px / TRAIL_SAMPLES) / (0.5 * drawn_px)
        ),
        "trail_covers_frame_step": trail_px >= max(travels),
        "trail_covers_frame_step_median": trail_px >= median,
    }


def _sample_disc(
    pixels: Any, width: int, height: int, cx: float, cy: float, radius: float
) -> list[float] | None:
    """Median RGB over a small disc, or None if the disc is off the frame."""
    channels: list[list[float]] = [[], [], []]
    step = max(1, int(radius / 3.0))
    span = int(math.ceil(radius))
    for dy in range(-span, span + 1, step):
        for dx in range(-span, span + 1, step):
            if dx * dx + dy * dy > radius * radius:
                continue
            x, y = int(round(cx + dx)), int(round(cy + dy))
            if not (0 <= x < width and 0 <= y < height):
                continue
            rgb = pixels[x, y]
            for channel in range(3):
                channels[channel].append(float(rgb[channel]))
    if not channels[0]:
        return None
    return [sorted(values)[len(values) // 2] for values in channels]


def still_report(
    document: dict[str, Any], png_path: str, width: int, height: int
) -> dict[str, Any]:
    """Read a rendered still back and report what is distinguishable in it.

    The still's name carries which moment it is; the *time* is recovered from
    the activated count the image shows, because a report that trusted the
    filename could not catch a renderer that drew the wrong instant.
    """
    from PIL import Image

    with Image.open(png_path) as handle:
        image = handle.convert("RGB")
        actual_width, actual_height = image.size
        pixels = image.load()

    scale = pixels_per_unit(document, actual_width)
    # Sample a disc a third of a tile's drawn length across, centred on the
    # tile's own midpoint pushed inwards to the middle of the drawn slab.
    radius = max(2.0, float(document["arena"]["tile_length"]) * scale * 0.16)

    inactive: list[float] = []
    active: list[float] = []
    per_tile: dict[str, float] = {}
    # Which tiles are lit is decided by counting the *image*, not by trusting a
    # time: the report is built for a given still and the still is the evidence.
    # So take the activation state from the brightest-N split the geometry
    # predicts, using the document's own activation order and the count the
    # frame shows. The count is recovered below from the split that maximises
    # separation, which is only well-defined because the two populations are
    # meant to be far apart - and if they are not, that is the finding.
    samples: list[tuple[int, float, list[float]]] = []
    for tile in document["arena"]["tiles"]:
        mid = tile["midpoint"]
        normal = tile["outward_normal"]
        inward = (
            mid[0] - normal[0] * 0.31,
            mid[1] - normal[1] * 0.31,
        )
        cx, cy = project(document, inward, actual_width, actual_height)
        rgb = _sample_disc(pixels, actual_width, actual_height, cx, cy, radius)
        if rgb is None:
            continue
        samples.append((int(tile["index"]), luminance(rgb), rgb))

    if not samples:
        raise ValueError(f"{png_path}: no tile fell inside the frame")

    ordered = sorted(samples, key=lambda entry: entry[1])
    # The largest luminance jump between consecutive tiles splits the two
    # populations. With a real inactive/activated distinction that jump is an
    # order of magnitude bigger than any within-population step.
    best_gap, split = 0.0, 0
    for index in range(1, len(ordered)):
        gap = ordered[index][1] - ordered[index - 1][1]
        if gap > best_gap:
            best_gap, split = gap, index

    # **A frame can legitimately hold only one population**, and the completion
    # still always does: all 51 tiles are lit, so there is no boundary to find
    # and the largest-gap rule splits ordinary within-population variation.
    # The first run of this report duly described the completed arena as "50
    # inactive tiles at luminance 244 and 1 active at 255", which is a
    # measurement of nothing. Below `SEPARATION_MIN_GAP` the split is refused
    # and the frame is reported as the single population it is.
    separable = best_gap >= SEPARATION_MIN_GAP
    if separable:
        dark, lit = ordered[:split], ordered[split:]
    elif ordered and ordered[len(ordered) // 2][1] >= SINGLE_POPULATION_LIT:
        dark, lit = [], ordered
    else:
        dark, lit = ordered, []

    for index, value, _rgb in samples:
        per_tile[str(index)] = round(value, 2)
    inactive = [value for _index, value, _rgb in dark]
    active = [value for _index, value, _rgb in lit]

    def median(values: list[float]) -> float:
        return sorted(values)[len(values) // 2] if values else 0.0

    brightest_inactive = max(inactive) if inactive else 0.0
    dimmest_active = min(active) if active else 0.0
    # Michelson contrast between the worst-case pair, which is what a viewer
    # hunting the last dark tile is actually up against.
    worst_pair = brightest_inactive + dimmest_active
    worst_contrast = (
        (dimmest_active - brightest_inactive) / worst_pair if worst_pair > 0 else 0.0
    )

    return {
        "path": os.path.basename(png_path),
        "frame": [actual_width, actual_height],
        "tiles_sampled": len(samples),
        "two_populations": separable,
        "inactive_tiles": len(inactive),
        "active_tiles": len(active),
        "inactive_luminance_median": round(median(inactive), 2),
        "active_luminance_median": round(median(active), 2),
        "brightest_inactive": round(brightest_inactive, 2),
        "dimmest_active": round(dimmest_active, 2),
        "population_gap": round(best_gap, 2),
        "worst_case_luminance_gap": (
            round(dimmest_active - brightest_inactive, 2) if separable else None
        ),
        "separation_ratio": (
            round(median(active) / median(inactive), 2)
            if separable and median(inactive) > 0
            else None
        ),
        "worst_case_michelson_contrast": (
            round(worst_contrast, 4) if separable else None
        ),
        # Only meaningful on a frame that really does show one dark tile. `None`
        # everywhere else, rather than a `True` that would read as a pass.
        "single_remaining_tile_identifiable": (
            None
            if not (separable and len(inactive) == 1)
            else dimmest_active - brightest_inactive > 20.0
        ),
        "per_tile_luminance": per_tile,
    }


def strobe_report(
    document: dict[str, Any],
    frame_paths: Sequence[str],
    fps: float,
    first_index: int = 0,
    background_margin: float = 6.0,
) -> dict[str, Any]:
    """Does the ball's drawn streak actually bridge the gap between frames?

    `motion_report` computes the gap and the nominal trail length and compares
    them, which is arithmetic over two constants. This reads the frames.

    For each consecutive pair, it walks the straight segment from where the ball
    was on frame `n-1` to where it is on frame `n` and samples frame `n` along
    it. If the trail is doing its job, every sample on that corridor is brighter
    than the background, because the streak drawn on frame `n` reaches back
    through all of it. If any sample falls to background, there is a dark gap
    between two consecutive positions of the ball, and that gap is the strobe.

    The corridor is sampled on the *later* frame only. Averaging the pair would
    let a bright frame `n-1` hide a hole in frame `n`, and a viewer does not see
    two frames at once - they see each one for 1/fps of a second.

    `background_margin` is how far above the arena's empty interior a sample has
    to be to count as lit. Six levels out of 255: above the PNG's own noise,
    far below anything the trail draws.
    """
    from PIL import Image

    if len(frame_paths) < 2:
        raise ValueError("a strobe report needs at least two consecutive frames")

    with Image.open(frame_paths[0]) as probe:
        width, height = probe.size
    # The arena interior, well inside the tile ring and away from the ball's
    # path at the sampled instants, is the background this compares against.
    # Taken from the image rather than from the colour constant, so glow and
    # tone-mapping are included in what "background" means.
    gaps: list[dict[str, Any]] = []
    worst_coverage = 1.0
    worst_pair = -1
    samples_per_pair = 24

    for offset in range(1, len(frame_paths)):
        with Image.open(frame_paths[offset]) as handle:
            image = handle.convert("RGB")
            pixels = image.load()
        index = first_index + offset
        here = tile_playback.position_at(document, index / fps)
        before = tile_playback.position_at(document, (index - 1) / fps)
        hx, hy = project(document, here, width, height)
        bx, by = project(document, before, width, height)

        # The interior reference: the arena centre, which no tile occupies and
        # which the ball is not at on either frame of any sampled pair.
        cx, cy = project(document, (0.0, 0.0), width, height)
        background = luminance(
            _sample_disc(pixels, width, height, cx, cy, 8.0) or (0.0, 0.0, 0.0)
        )

        lit = 0
        darkest = 255.0
        for step in range(samples_per_pair + 1):
            u = step / samples_per_pair
            sx = bx + (hx - bx) * u
            sy = by + (hy - by) * u
            rgb = _sample_disc(pixels, width, height, sx, sy, 3.0)
            if rgb is None:
                continue
            value = luminance(rgb)
            darkest = min(darkest, value)
            if value > background + background_margin:
                lit += 1
        coverage = lit / (samples_per_pair + 1)
        if coverage < worst_coverage:
            worst_coverage, worst_pair = coverage, index
        if coverage < 1.0:
            gaps.append(
                {
                    "frame": index,
                    "coverage": round(coverage, 3),
                    "darkest_on_corridor": round(darkest, 2),
                    "background": round(background, 2),
                    "step_px": round(math.dist((bx, by), (hx, hy)), 1),
                }
            )

    return {
        "fps": fps,
        "pairs_tested": len(frame_paths) - 1,
        "pairs_with_a_gap": len(gaps),
        "continuous": not gaps,
        "worst_coverage": round(worst_coverage, 3),
        "worst_coverage_frame": worst_pair,
        "gaps": gaps[:8],
    }


def compare_audit(document: dict[str, Any], audit_path: str) -> dict[str, Any]:
    """Compare what Godot drew against what the solver said.

    Three things have to agree, and they fail in different ways:

    - the **order** the tiles lit in, which a renderer could scramble by
      keeping its own activation set;
    - the **frame** each tile first appeared lit on, which a renderer could get
      one out by accumulating `delta` instead of indexing frames;
    - the **ball position** at every frame, which is the trajectory itself.

    The position tolerance is `1e-9` world units, not a visual tolerance. The
    renderer evaluates the same closed form on the same doubles, so the only
    difference permitted is GDScript reading a JSON double - which is exact.
    Anything larger means the renderer computed rather than replayed.
    """
    with open(audit_path, "r", encoding="utf-8") as handle:
        audit = json.load(handle)
    if audit.get("kind") != "category3_tile_escape_audit":
        raise tile_playback.PlaybackMismatch(f"{audit_path} is not an audit")
    if audit["digest"] != document["digest"]:
        raise tile_playback.PlaybackMismatch(
            f"{audit_path} audits digest {audit['digest'][:16]}, the document is "
            f"{document['digest'][:16]}"
        )

    fps = float(audit["fps"])
    expected_frames = tile_playback.activation_frames(document, fps)
    expected_order = [entry["tile"] for entry in document["activations"]]

    first_lit = {int(key): int(value) for key, value in audit["first_lit_frame"].items()}
    drawn_order = [tile for tile, _frame in sorted(first_lit.items(), key=lambda kv: (kv[1], kv[0]))]

    frame_mismatches: list[dict[str, Any]] = []
    for tile, frame in zip(expected_order, expected_frames):
        drawn = first_lit.get(tile)
        if drawn != frame:
            frame_mismatches.append({"tile": tile, "expected": frame, "drawn": drawn})

    max_error = 0.0
    worst_frame = -1
    times = audit["sample_t"]
    xs, ys = audit["sample_x"], audit["sample_y"]
    for index in range(len(times)):
        ex, ey = tile_playback.position_at(document, float(times[index]))
        error = math.dist((float(xs[index]), float(ys[index])), (ex, ey))
        if error > max_error:
            max_error, worst_frame = error, index

    # The order the renderer drew tiles in must be the canonical order, but two
    # tiles activating inside the same frame are indistinguishable on screen
    # and are compared as a set rather than as a sequence.
    order_matches = True
    if len(drawn_order) != len(expected_order):
        order_matches = False
    else:
        position = 0
        for frame in sorted(set(expected_frames)):
            size = sum(1 for f in expected_frames if f == frame)
            expected_group = set(expected_order[position:position + size])
            drawn_group = set(drawn_order[position:position + size])
            if expected_group != drawn_group:
                order_matches = False
                break
            position += size

    frames_match = not frame_mismatches
    counts_match = int(audit["final_activated"]) == int(document["activated_tiles"])
    positions_match = max_error <= 1.0e-9

    return {
        "seed": int(audit["seed"]),
        "fps": fps,
        "frames": int(audit["frames"]),
        "total_tiles": int(audit["total_tiles"]),
        "final_activated": int(audit["final_activated"]),
        "activation_order_matches": order_matches,
        "activation_frames_match": frames_match,
        "activation_frame_mismatches": frame_mismatches[:8],
        "activation_count_matches": counts_match,
        "max_position_error_wu": max_error,
        "max_position_error_frame": worst_frame,
        "positions_match": positions_match,
        "pixels_per_unit_matches": (
            abs(float(audit["pixels_per_unit"])
                - pixels_per_unit(document, int(audit["width"]))) < 1.0e-6
        ),
        "playback_matches": (
            order_matches and frames_match and counts_match and positions_match
        ),
    }

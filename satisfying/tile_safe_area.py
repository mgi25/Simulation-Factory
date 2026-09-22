"""The Shorts safe area: what the player's own UI covers, and what that hides.

A vertical video is not shown on a blank 9:16 rectangle. YouTube Shorts draws
its own controls over the top of it - an action rail down the right side, a
title and channel block across the bottom, a progress bar under that - and
every pixel of the video underneath them is, for practical purposes, not there.
A composition that is legible as a PNG can still lose the one thing the viewer
needs to see.

This module answers that as arithmetic and as a picture, in that order.

## The regions are a conservative model, not a reproduction

They are deliberately **larger** than the real controls, and they are stated as
fractions of the frame so they hold at any resolution. Reproducing YouTube's
layout exactly would be the wrong target twice over: it changes between client
versions, and a composition that only just survives today's layout is not
safe. So `SHORTS_REGIONS` over-covers, and a target that clears these rectangles
clears the real thing with room to spare.

Sources for the shape of the model, all of them observational rather than
specified: the action rail sits against the right edge and runs from roughly
the vertical middle to the bottom of the safe area; the title, channel name and
avatar occupy a band across the bottom left; a thin scrubber sits below that;
and on phones the app's own navigation bar takes the very bottom of the screen.
The one region that is *not* over-drawn is the top: Shorts puts little there,
and drawing a large top exclusion would falsely condemn the hook.

## Three models, and only one of them is a gate

`shorts_measured` is the strip as it measures on a screenshot with no margin
added. `shorts_conservative` is that plus about 20 dp on the left, and it is
**the gate** - the model a composition has to clear. `shorts_strict` adds
another 30 dp and reaches higher, and it is a stress test: its job is to say
how much further the player could grow before the composition would have to
move again, and it is deliberately hard enough that a passing composition can
still fail it.

That distinction is load-bearing. An over-drawn model used as a gate drives the
design rather than informing it: satisfying `shorts_strict` centred would cost
a quarter of the arena's scale, which is a worse outcome than the exposure it
prevents. So `report` measures all three, `tile_phase6_cli safearea` prints
PASS/FAIL only for the gate, and the other two print as margin readings.

## What "covered" means

Two different questions, and they need different instruments.

**Geometry**, for the tiles and the arena. Every tile is a known quadrilateral
in the frame - `tile_readability.project` puts it there from the playback
document's own numbers - so the fraction of a tile's drawn face that falls
inside a region is exact and needs no render. `tile_exposure` is that.

**Pixels**, for the text. The hook and the counter are drawn by Godot's font
engine at a size this module does not know, so where they actually land is a
fact about a rendered frame and is measured by reading one back. `text_extent`
finds the bright type in a band and returns its bounding box.

The ball is geometry again, but over time rather than at an instant:
`ball_exposure` walks the playback and reports how much of the run the ball
spends underneath each region, and - the reading that matters - the longest
single stretch it is hidden for.

## The decision this module exists to support

Phase 6 needed one number to decide whether the composition had to move: is any
*critical target* - the ball, the last dark tile, the counter, the hook, the
gate, the escape - covered at a moment when the viewer needs it? Everything
here is in service of that question, and `report` assembles it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import Any, Sequence

from satisfying import tile_playback, tile_readability

__all__ = [
    "SAFE_AREA_FORMAT",
    "SafeAreaError",
    "Region",
    "SHORTS_REGIONS",
    "SafeAreaConfig",
    "DEFAULT_SAFE_AREA",
    "named_safe_area",
    "region_rects",
    "tile_exposure",
    "ball_exposure",
    "text_extent",
    "overlay_frame",
    "report",
]

SAFE_AREA_FORMAT = 1


class SafeAreaError(RuntimeError):
    """A safe-area configuration or frame that cannot be measured."""


@dataclass(frozen=True)
class Region:
    """One rectangle of the player's UI, in fractions of the frame.

    `left`/`top`/`right`/`bottom` are fractions in [0, 1], with the origin at
    the frame's top left - the same convention `tile_readability.project` uses,
    so a projected point and a region can be compared without a flip.
    """

    name: str
    left: float
    top: float
    right: float
    bottom: float
    # What the real control is, so a reader can judge whether the model is
    # honest without having the app open.
    note: str = ""

    def __post_init__(self) -> None:
        for field in ("left", "top", "right", "bottom"):
            value = getattr(self, field)
            if not 0.0 <= value <= 1.0:
                raise SafeAreaError(
                    f"region {self.name!r}: {field} is {value}, not a fraction"
                )
        if self.right <= self.left or self.bottom <= self.top:
            raise SafeAreaError(f"region {self.name!r} is empty or inverted")

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def rect(self, width: int, height: int) -> tuple[float, float, float, float]:
        return (self.left * width, self.top * height,
                self.right * width, self.bottom * height)

    def contains(self, x: float, y: float, width: int, height: int) -> bool:
        left, top, right, bottom = self.rect(width, height)
        return left <= x <= right and top <= y <= bottom


# The model, derived in device-independent pixels on a 412 dp viewport - the
# width the Shorts player lays out against on a typical phone - and then
# expressed as fractions so it holds at any render size.
#
# `action_rail`. The icon column is right-aligned: each control is a ~24 dp
# glyph in a ~48 dp target, the column's right edge sits ~10 dp off the screen
# edge, and a count sits under each icon. That puts the real blocked strip at
# roughly dp 354-402, or x 0.859-0.976. Rounded outward to **0.84-1.00**: the
# extra 20 dp on the left is the margin, and extending to the right edge costs
# nothing because there is nothing out there to protect. Vertically the top
# control sits a little under half height and the disc ends just above the
# title, so 0.42-0.93 covers it with room.
#
# `title_block`. Avatar, @handle and up to three lines of title, bottom left,
# ending where the scrubber begins. This is the region that most often
# surprises a composition, because it is where a designer naturally puts a
# caption.
#
# `progress_bar`. The scrubber, full width, thin.
#
# `nav_bar`. The app's own Home/Shorts/Subscriptions/You row. Not part of the
# player at all, which is exactly why it is easy to forget.
#
# `top_bar`. The Shorts wordmark and the search and camera icons. Deliberately
# shallow: over-drawing here would condemn a hook that is in fact perfectly
# visible, and Shorts puts very little at the top.
SHORTS_REGIONS: tuple[Region, ...] = (
    Region("action_rail", 0.840, 0.420, 1.000, 0.930,
           "like / dislike / comment / share / remix / sound disc, plus counts"),
    Region("title_block", 0.000, 0.840, 0.840, 0.940,
           "avatar, @handle and up to three lines of title"),
    Region("progress_bar", 0.000, 0.940, 1.000, 0.960,
           "the scrubber"),
    Region("nav_bar", 0.000, 0.960, 1.000, 1.000,
           "the app's own navigation row, not the player's"),
    Region("top_bar", 0.000, 0.000, 1.000, 0.060,
           "the Shorts wordmark, search and camera"),
)


@dataclass(frozen=True)
class SafeAreaConfig:
    """Which regions apply, and how strictly a target has to clear them."""

    name: str = "shorts_conservative"
    regions: tuple[Region, ...] = SHORTS_REGIONS
    # A tile counts as obstructed when this much of its drawn face is inside a
    # region. 0.25 rather than 0.5: a quarter of a tile under an icon is
    # already enough to make "is that one lit?" a guess, and the whole point of
    # the late game is that the viewer is hunting one dark tile.
    tile_obstructed_fraction: float = 0.25
    # The ball is a disc; this is how much of it may be covered before it
    # counts as hidden.
    ball_hidden_fraction: float = 0.50
    # How long the ball may be continuously hidden before it is a defect.
    # 0.25 s is about eight frames at 30 fps - long enough that the eye loses
    # the object rather than blinking past it.
    ball_hidden_budget_seconds: float = 0.250
    # Sampled at the render rate, so the answer is about frames a viewer sees.
    fps: float = 30.0

    def __post_init__(self) -> None:
        if not self.regions:
            raise SafeAreaError("a safe area with no regions tests nothing")
        names = [region.name for region in self.regions]
        if len(names) != len(set(names)):
            raise SafeAreaError("region names must be unique")
        if not 0.0 < self.tile_obstructed_fraction <= 1.0:
            raise SafeAreaError("tile_obstructed_fraction must be in (0, 1]")
        if not 0.0 < self.ball_hidden_fraction <= 1.0:
            raise SafeAreaError("ball_hidden_fraction must be in (0, 1]")
        if self.ball_hidden_budget_seconds < 0.0:
            raise SafeAreaError("the hidden budget cannot be negative")
        if self.fps <= 0.0:
            raise SafeAreaError("fps must be positive")

    def as_dict(self) -> dict[str, Any]:
        out = {
            key: value for key, value in self.__dict__.items()
            if key != "regions"
        }
        out["regions"] = [region.as_dict() for region in self.regions]
        return out

    def fingerprint(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


DEFAULT_SAFE_AREA = SafeAreaConfig()

# One looser variant, for the question "would a smaller arena help?" to be
# answerable against something other than the strict model.
SAFE_AREAS: dict[str, SafeAreaConfig] = {
    "shorts_conservative": DEFAULT_SAFE_AREA,
    # The strip as it actually measures on a screenshot, with no margin added.
    # Not the gate - it exists so a reading against the model above can be
    # split into "the UI covers this" and "the margin covers this".
    "shorts_measured": SafeAreaConfig(
        name="shorts_measured",
        regions=(
            Region("action_rail", 0.859, 0.440, 0.976, 0.910,
                   "as measured, no margin added"),
            Region("title_block", 0.000, 0.855, 0.859, 0.935, "as measured"),
            Region("progress_bar", 0.000, 0.935, 1.000, 0.955, "as measured"),
            Region("nav_bar", 0.000, 0.955, 1.000, 1.000, "as measured"),
            Region("top_bar", 0.000, 0.000, 1.000, 0.050, "as measured"),
        ),
    ),
    # A deliberate stress test: the rail 20 dp wider again and reaching higher.
    # Used to report how much margin a passing composition still has, never to
    # decide whether it passes.
    "shorts_strict": SafeAreaConfig(
        name="shorts_strict",
        regions=(
            Region("action_rail", 0.810, 0.380, 1.000, 0.940, "stress test"),
            Region("title_block", 0.000, 0.815, 0.810, 0.945, "stress test"),
            Region("progress_bar", 0.000, 0.945, 1.000, 0.962, "stress test"),
            Region("nav_bar", 0.000, 0.962, 1.000, 1.000, "stress test"),
            Region("top_bar", 0.000, 0.000, 1.000, 0.070, "stress test"),
        ),
    ),
}


def named_safe_area(name: str, **overrides: Any) -> SafeAreaConfig:
    if name not in SAFE_AREAS:
        raise SafeAreaError(
            f"unknown safe area {name!r}; known: {sorted(SAFE_AREAS)}")
    base = SAFE_AREAS[name]
    return dataclasses.replace(base, **overrides) if overrides else base


def region_rects(config: SafeAreaConfig,
                 width: int,
                 height: int) -> dict[str, tuple[float, float, float, float]]:
    """Every region in pixels, for compositing and for reporting."""
    return {region.name: region.rect(width, height) for region in config.regions}


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def _tile_quad(document: dict[str, Any],
               index: int,
               width: int,
               height: int) -> list[tuple[float, float]]:
    """A tile's drawn face in pixels.

    The drawn face, not the collision segment: `TILE_GAP_FRACTION` of the
    length is trimmed from each end by the renderer, and the radial thickness
    is what makes it a quadrilateral rather than a line. Both constants are
    mirrored from `tile_escape_scene.gd` in `tile_readability`, which is the
    one place Category 3 keeps the renderer's numbers on the Python side.
    """
    tile = document["arena"]["tiles"][index]
    start = [float(value) for value in tile["start"]]
    end = [float(value) for value in tile["end"]]
    gap = tile_readability.TILE_GAP_FRACTION
    inner = [
        (start[0] + (end[0] - start[0]) * gap, start[1] + (end[1] - start[1]) * gap),
        (start[0] + (end[0] - start[0]) * (1.0 - gap),
         start[1] + (end[1] - start[1]) * (1.0 - gap)),
    ]
    # Outward normal: a tile's midpoint points away from the centre.
    midpoint = [float(value) for value in tile["midpoint"]]
    length = math.hypot(midpoint[0], midpoint[1]) or 1.0
    normal = (midpoint[0] / length, midpoint[1] / length)
    thickness = tile_readability.TILE_RADIAL_THICKNESS
    corners = [
        inner[0],
        inner[1],
        (inner[1][0] + normal[0] * thickness, inner[1][1] + normal[1] * thickness),
        (inner[0][0] + normal[0] * thickness, inner[0][1] + normal[1] * thickness),
    ]
    return [tile_readability.project(document, corner, width, height)
            for corner in corners]


def _quad_coverage(quad: Sequence[tuple[float, float]],
                   region: Region,
                   width: int,
                   height: int,
                   samples: int = 12) -> float:
    """The fraction of a quadrilateral inside a region, by bilinear sampling.

    A grid rather than a polygon clip: the quad is convex and nearly a
    rectangle, `samples**2` points give a resolution of better than one percent
    of its area, and the result is exactly reproducible - which a clipping
    routine with its own tolerances would not be.
    """
    inside = 0
    total = 0
    for i in range(samples):
        u = (i + 0.5) / samples
        top_x = quad[0][0] + (quad[1][0] - quad[0][0]) * u
        top_y = quad[0][1] + (quad[1][1] - quad[0][1]) * u
        bottom_x = quad[3][0] + (quad[2][0] - quad[3][0]) * u
        bottom_y = quad[3][1] + (quad[2][1] - quad[3][1]) * u
        for j in range(samples):
            v = (j + 0.5) / samples
            x = top_x + (bottom_x - top_x) * v
            y = top_y + (bottom_y - top_y) * v
            total += 1
            if region.contains(x, y, width, height):
                inside += 1
    return inside / total if total else 0.0


def tile_exposure(document: dict[str, Any],
                  config: SafeAreaConfig = DEFAULT_SAFE_AREA,
                  width: int = 1080,
                  height: int = 1920) -> dict[str, Any]:
    """How much of each tile the UI covers, and which tiles are obstructed."""
    total_tiles = int(document["total_tiles"])
    per_tile: list[dict[str, Any]] = []
    for index in range(total_tiles):
        quad = _tile_quad(document, index, width, height)
        covered: dict[str, float] = {}
        for region in config.regions:
            fraction = _quad_coverage(quad, region, width, height)
            if fraction > 0.0:
                covered[region.name] = round(fraction, 4)
        worst = max(covered.values()) if covered else 0.0
        per_tile.append({
            "tile": index,
            "side": int(document["arena"]["tiles"][index]["side"]),
            "slot": int(document["arena"]["tiles"][index]["slot"]),
            "covered": covered,
            "worst_fraction": round(worst, 4),
            "obstructed": worst >= config.tile_obstructed_fraction,
        })
    obstructed = [row["tile"] for row in per_tile if row["obstructed"]]
    touched = [row["tile"] for row in per_tile if row["worst_fraction"] > 0.0]
    return {
        "tiles": per_tile,
        "obstructed_tiles": obstructed,
        "obstructed_count": len(obstructed),
        "touched_count": len(touched),
        "worst_tile": max(per_tile, key=lambda row: row["worst_fraction"]),
    }


def ball_exposure(document: dict[str, Any],
                  config: SafeAreaConfig = DEFAULT_SAFE_AREA,
                  width: int = 1080,
                  height: int = 1920) -> dict[str, Any]:
    """How much of the run the ball spends under the UI.

    Sampled on the frame grid, because a frame is the unit a viewer sees. The
    drawn radius is used rather than the collision radius: what can be hidden
    is what is drawn.
    """
    scale = tile_readability.pixels_per_unit(document, width)
    radius = (float(document["config"]["ball_radius"])
              * tile_readability.BALL_DRAW_SCALE * scale)
    end = float(document.get("completion_seconds")
                or document["end_seconds"])
    frames = int(math.floor(end * config.fps)) + 1
    hidden_frames = 0
    longest = 0
    current = 0
    longest_at = 0.0
    by_region: dict[str, int] = {region.name: 0 for region in config.regions}
    for frame in range(frames):
        t = frame / config.fps
        point = tile_playback.position_at(document, t)
        x, y = tile_readability.project(document, point, width, height)
        worst = 0.0
        worst_name = ""
        for region in config.regions:
            fraction = _disc_coverage(x, y, radius, region, width, height)
            if fraction > 0.0:
                by_region[region.name] = by_region.get(region.name, 0) + 1
            if fraction > worst:
                worst = fraction
                worst_name = region.name
        if worst >= config.ball_hidden_fraction:
            hidden_frames += 1
            current += 1
            if current > longest:
                longest = current
                longest_at = t
        else:
            current = 0
    return {
        "frames": frames,
        "hidden_frames": hidden_frames,
        "hidden_pct": round(100.0 * hidden_frames / max(1, frames), 3),
        "longest_hidden_frames": longest,
        "longest_hidden_seconds": round(longest / config.fps, 4),
        "longest_hidden_ends_at": round(longest_at, 3),
        "budget_seconds": config.ball_hidden_budget_seconds,
        "within_budget": (longest / config.fps
                          <= config.ball_hidden_budget_seconds),
        "frames_touching_region": by_region,
    }


def _disc_coverage(x: float,
                   y: float,
                   radius: float,
                   region: Region,
                   width: int,
                   height: int,
                   rings: int = 6,
                   spokes: int = 12) -> float:
    """The fraction of a disc inside a region, by area-weighted sampling."""
    if radius <= 0.0:
        return 1.0 if region.contains(x, y, width, height) else 0.0
    inside = 0.0
    total = 0.0
    for ring in range(rings):
        # Equal-area rings: r = R * sqrt((k + 0.5) / rings).
        r = radius * math.sqrt((ring + 0.5) / rings)
        for spoke in range(spokes):
            angle = 2.0 * math.pi * spoke / spokes
            total += 1.0
            if region.contains(x + r * math.cos(angle),
                               y + r * math.sin(angle), width, height):
                inside += 1.0
    return inside / total if total else 0.0


# --------------------------------------------------------------------------
# Pixels, for the text
# --------------------------------------------------------------------------


def text_extent(png_path: str,
                top_fraction: float,
                bottom_fraction: float,
                threshold: float = 90.0) -> dict[str, Any]:
    """The bounding box of the bright type in a horizontal band of a frame.

    Used for the hook and the counter, whose positions are decided by Godot's
    font metrics rather than by anything on the Python side. The threshold is a
    luminance, and it is well above the arena's own dark background and well
    below the type's own white - `still_report` reads inactive tiles at about
    20 and the type is drawn at the overlay's primary colour.
    """
    from PIL import Image

    if not os.path.isfile(png_path):
        raise SafeAreaError(f"no frame at {png_path}")
    with Image.open(png_path) as handle:
        image = handle.convert("RGB")
        width, height = image.size
        top = max(0, int(top_fraction * height))
        bottom = min(height, int(bottom_fraction * height))
        if bottom <= top:
            raise SafeAreaError("an empty band cannot contain type")
        crop = image.crop((0, top, width, bottom))
        pixels = crop.load()
        min_x, min_y, max_x, max_y = width, bottom, -1, -1
        count = 0
        for y in range(bottom - top):
            for x in range(width):
                if tile_readability.luminance(pixels[x, y]) >= threshold:
                    count += 1
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y + top < min_y:
                        min_y = y + top
                    if y + top > max_y:
                        max_y = y + top
    if count == 0:
        return {"found": False, "band": [top_fraction, bottom_fraction],
                "pixels": 0}
    return {
        "found": True,
        "pixels": count,
        "frame": [width, height],
        "box_px": [min_x, min_y, max_x, max_y],
        "box_fraction": [round(min_x / width, 4), round(min_y / height, 4),
                         round(max_x / width, 4), round(max_y / height, 4)],
        "width_px": max_x - min_x + 1,
        "height_px": max_y - min_y + 1,
        "centre_fraction": [round(0.5 * (min_x + max_x) / width, 4),
                            round(0.5 * (min_y + max_y) / height, 4)],
    }


def text_clearance(extent: dict[str, Any],
                   config: SafeAreaConfig = DEFAULT_SAFE_AREA) -> dict[str, Any]:
    """Which regions a measured text box intersects, and by how much."""
    if not extent.get("found"):
        return {"found": False}
    left, top, right, bottom = extent["box_fraction"]
    hits: dict[str, float] = {}
    for region in config.regions:
        overlap_x = max(0.0, min(right, region.right) - max(left, region.left))
        overlap_y = max(0.0, min(bottom, region.bottom) - max(top, region.top))
        area = max(1.0e-12, (right - left) * (bottom - top))
        if overlap_x > 0.0 and overlap_y > 0.0:
            hits[region.name] = round(overlap_x * overlap_y / area, 4)
    return {
        "found": True,
        "box_fraction": extent["box_fraction"],
        "intersects": hits,
        "worst_fraction": round(max(hits.values()), 4) if hits else 0.0,
        "clear": not hits,
    }


# --------------------------------------------------------------------------
# The picture
# --------------------------------------------------------------------------


def overlay_frame(png_in: str,
                  png_out: str,
                  config: SafeAreaConfig = DEFAULT_SAFE_AREA,
                  alpha: float = 0.55,
                  label: str = "") -> str:
    """Composite the UI model over a frame, so the arithmetic can be checked.

    A proof, not a mock-up: flat translucent blocks with their names on them.
    Drawing convincing icons would invite the reader to judge the imitation
    instead of the clearance.
    """
    from PIL import Image, ImageDraw

    if not os.path.isfile(png_in):
        raise SafeAreaError(f"no frame at {png_in}")
    with Image.open(png_in) as handle:
        base = handle.convert("RGB")
    width, height = base.size
    shade = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shade)
    fill = int(max(0.0, min(1.0, alpha)) * 255)
    for region in config.regions:
        left, top, right, bottom = region.rect(width, height)
        draw.rectangle([left, top, right, bottom], fill=(255, 42, 90, fill))
        draw.rectangle([left, top, right, bottom], outline=(255, 255, 255, 220),
                       width=max(2, width // 400))
        draw.text((left + 12, top + 10), region.name.upper(),
                  fill=(255, 255, 255, 255))
    if label:
        draw.text((16, height - 28), label, fill=(255, 255, 255, 255))
    out = Image.alpha_composite(base.convert("RGBA"), shade).convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(png_out)) or ".", exist_ok=True)
    out.save(png_out)
    return png_out


# --------------------------------------------------------------------------
# The whole answer
# --------------------------------------------------------------------------


def report(document: dict[str, Any],
           config: SafeAreaConfig = DEFAULT_SAFE_AREA,
           width: int = 1080,
           height: int = 1920,
           final_tile: int | None = None) -> dict[str, Any]:
    """Everything the decision needs, as one JSON-able block."""
    tiles = tile_exposure(document, config, width, height)
    ball = ball_exposure(document, config, width, height)
    geometry = tile_readability.frame_geometry(document, width, height)
    if final_tile is None and document.get("completion"):
        final_tile = int(document["completion"]["final_tile"])
    final_row = None
    if final_tile is not None:
        final_row = tiles["tiles"][final_tile]
    # The activation order decides which tiles are still dark late in the run,
    # which is the only time an obstructed tile can actually cost anything.
    order = [int(entry["tile"]) for entry in document["activations"]]
    late = order[-4:] if len(order) >= 4 else order
    return {
        "format": SAFE_AREA_FORMAT,
        "safe_area": config.name,
        "fingerprint": config.fingerprint(),
        "frame": [width, height],
        "regions": {name: [round(value, 2) for value in rect]
                    for name, rect in region_rects(config, width, height).items()},
        "arena": {
            "left_px": round(width * 0.5 - 0.5 * geometry["arena_width_px"], 2),
            "right_px": round(width * 0.5 + 0.5 * geometry["arena_width_px"], 2),
            "top_px": round(geometry["arena_top_px"], 2),
            "bottom_px": round(geometry["arena_bottom_px"], 2),
            "width_fraction": round(geometry["arena_occupancy_width"], 4),
        },
        "tiles": {
            "obstructed_tiles": tiles["obstructed_tiles"],
            "obstructed_count": tiles["obstructed_count"],
            "touched_count": tiles["touched_count"],
            "worst_tile": tiles["worst_tile"],
        },
        "final_tile": final_row,
        "last_four_activated": [tiles["tiles"][index] for index in late],
        "ball": ball,
        "per_tile": tiles["tiles"],
    }

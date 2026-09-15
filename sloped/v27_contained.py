"""V27: what the contained-stage lab compares, and what it measures it with.

**V27 changes one string.** `sloped/v26.py` names the world it renders in one
assignment - `ENVIRONMENT = "aurora_valley_v26"` - and every concept in this
lab is that assignment with a different value. The replay is seed 5432's, the
camera track is `cameras_v24_5432.json`, the edit is V24's, the machine is
V23B's and the racer surface is `meridian`, in every render here. So a
difference between two sheets in this file is a difference of pixels and of
nothing else: no moment has to be found twice and no timing can have moved.

## The instrument is V25's

`segment`, `band_shift`, `parallax`, `monotone`, `separation`, `phone`,
`noise` and `parse_cost` are imported from :mod:`sloped.v25_world` rather than
rewritten. The rule the world labs settled on is that a control has to be
measured by the instrument that measured the thing it is a control for, or a
difference in a sheet could be a difference in the ruler - and here the control
is V26's outdoor world, which that instrument judged.

What is new is the **band table**, because the bands are different objects: a
contained stage has no ridges and no distant range, it has a floor, a wall and
the structure between them. :data:`LAYERS` and :data:`MARKED` say which.

## The one measurement this pass exists to have taken

:func:`visible_ceiling` - the highest point at a given plan position that lies
inside *any* V26 frame. It is not a metric for scoring a concept; it is a fact
about the camera track, and it decides where architecture is worth building at
all.

These cameras stand at elevations of 30 to 54 degrees with vertical fields of
34 to 36, so the **top edge of every frame is at least 4.7 degrees below
horizontal** - measured, at replay 14.02 in the second obstacle cut, which is
the shallowest frame in the film. Nothing above a camera's own eye height is ever in shot. Two
consequences fall straight out of it and both are in
``docs/sloped_race_v27_contained.md``:

    a ceiling over the machine is invisible at every radius, and
    bearings 225 to 285 are never in any frame, and past radius 110
    only 315 through 195 is.

Neither is a matter of taste and neither could be seen in a still.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sloped import v25_world
from sloped.v25_world import (  # noqa: F401  (re-exported: V25's instrument)
    CHROMA_FLOOR,
    PHONE,
    Cost,
    band_shift,
    census_of,
    median,
    monotone,
    noise,
    parallax,
    parse_cost,
    phone,
    separation,
    table,
)

__all__ = [
    "ALL",
    "CONTROL",
    "CONCEPTS",
    "LAYERS",
    "MARKED",
    "MARKERS",
    "MOMENTS",
    "PARALLAX_PAIRS",
    "CLIPS",
    "CRITERIA",
    "HOOK_BOX",
    "concept",
    "marker",
    "moment",
    "layer",
    "seconds",
    "segment",
    "layer_cover",
    "layer_value",
    "recession",
    "visible_ceiling",
    "frames_of",
]

SEED = 5432
FPS = 60
WIDTH, HEIGHT = 1080, 1920

#: The terrain's own plan centre, from `course_layout.B_TERRAIN`. Every radius
#: and bearing in this module and in the three profiles is measured from here,
#: because that is what `environment_world` and `environment_stage` place
#: against.
CENTRE = (1.0, 6.0)


# --- the concepts -----------------------------------------------------------


@dataclass(frozen=True)
class Concept:
    """One contained-environment direction, as the lab refers to it.

    `key` is the string handed to Godot as `--environment=`; it must name a
    profile in `environment/profiles/index.json`, and
    `tests/test_sloped_v27_contained.py` checks that the two lists agree.
    """

    key: str
    tag: str
    title: str
    blurb: str


CONTROL = Concept(
    "aurora_valley_v26",
    "v26",
    "V26 control - outdoor canyon",
    "the accepted production world: V25.2's stylised valley with the finish "
    "sightline cleared. Nothing about it is changed by this pass.",
)

CONCEPTS: tuple[Concept, ...] = (
    Concept(
        "contained_hall",
        "a",
        "A - Premium machine hall",
        "a round graphite drum at radius 122 with a 32-segment rhythm of "
        "ribs, recessed bays and light slots, a second wall below the floor "
        "line, two deck bands and a ring of braced columns",
    ),
    Concept(
        "diorama_chamber",
        "b",
        "B - Toy diorama chamber",
        "an eighteen-lobed chamber at radius 104/113 with large sculpted "
        "niches, a heavy cornice and plinth, a broad display platform the "
        "landform stands on, and no overhead structure at all",
    ),
    Concept(
        "industrial_chamber",
        "c",
        "C - Enclosed industrial canyon",
        "two tall slab walls at radius 88 facing each other across the "
        "course, a deep back wall at 140, a truss line of twelve legs and "
        "two bridge groups crossing overhead",
    ),
)

ALL: tuple[Concept, ...] = (CONTROL,) + CONCEPTS

#: The diagnostic twin of each concept: the same geometry with every stage
#: surface painted the flat hue of its depth band. Not a look - it is what
#: `segment`, `layer_cover` and `parallax` are read off, so that depth is
#: measured from a segmentation of the real render rather than guessed.
MARKERS: dict[str, str] = {
    "contained_hall": "_marker_v27a",
    "diorama_chamber": "_marker_v27b",
    "industrial_chamber": "_marker_v27c",
    # The control's marker already exists: V25 wrote one over `aurora_valley`,
    # and V26's world is a delta over V25.2's, so the control needs its own.
    "aurora_valley_v26": "_marker_v27_control",
}


def concept(key: str) -> Concept:
    for entry in ALL:
        if entry.key == key or entry.tag == key:
            return entry
    raise KeyError(f"no V27 concept named {key!r}")


def marker(key: str) -> str:
    resolved = concept(key).key
    if resolved not in MARKERS:
        raise KeyError(f"no V27 marker for {resolved!r}")
    return MARKERS[resolved]


# --- the frames -------------------------------------------------------------


@dataclass(frozen=True)
class Moment:
    """One comparison frame: an output second, and why it is worth a cell."""

    key: str
    second: float
    replay: float
    title: str
    why: str


#: The twelve the brief names, as **output** seconds on V24's own edit.
#:
#: They are computed rather than guessed: `sloped/v26.py` re-exports V24's edit
#: map, every one of these seconds is inside the cut that owns it, and
#: `tests/test_sloped_v27_contained.py` re-derives each from the delivered
#: camera track and fails if a cut boundary ever moves. The `replay` column is
#: the race instant the film shows at that second, and the two differ because
#: V24 omits 3.133 s of racing.
#:
#: The V26 edit, in output seconds, for anyone checking the arithmetic:
#:
#:     hook 0.000-1.400   start 1.400-1.850   start 1.850-3.800
#:     descent 3.800-6.767   obstacle 6.767-10.683   obstacle 10.683-11.767
#:     fork 11.767-13.400   branches 13.400-15.083   merge 15.083-15.567
#:     final 15.567-20.117
MOMENTS: tuple[Moment, ...] = (
    Moment("frame0", 0.000, 0.200, "1  Frame 0",
           "the hook. Eight racers on the line under the START gantry, and "
           "the frame the PICK A COLOR card sits on"),
    Moment("mixer", 2.783, 5.400, "2  Mixer",
           "the rotor turning, with the hillside above the start filling the "
           "upper third"),
    Moment("release", 3.683, 6.300, "3  Release",
           "the trapdoor, the last frame before the pack is a pack"),
    Moment("descent", 5.100, 8.000, "4  Descent",
           "the first shot with ground above and the gorge below at once"),
    Moment("obstacle", 9.600, 12.500, "5  Obstacle",
           "the longest cut, and the section the brief calls the weakest: "
           "nothing here has a local identity"),
    Moment("fork_approach", 11.967, 15.300, "6  Fork approach",
           "the gate coming up, with the route choice not yet made"),
    Moment("split", 12.567, 15.900, "7  Split",
           "the choice itself, where architecture can state it twice"),
    Moment("branch", 14.067, 17.400, "8  Branch",
           "two routes over open air: the depth shot of the whole film, and "
           "the one a floored chamber would destroy"),
    Moment("merge", 15.267, 18.600, "9  Merge",
           "the routes rejoining, with the finish already in frame"),
    Moment("final_approach", 16.467, 19.800, "10  Final approach",
           "the run at the line, the lowest the course ever gets"),
    Moment("winner", 17.517, 20.850, "11  Winner crossing",
           "the payoff instant: the WINNER ring comes up on this frame"),
    Moment("payoff", 18.500, 21.833, "12  Payoff",
           "the card is up and the field is still arriving; what is behind "
           "the end plate"),
)


def moment(key: str) -> Moment:
    for entry in MOMENTS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V27 moment named {key!r}")


def seconds() -> tuple[float, ...]:
    return tuple(one.second for one in MOMENTS)


#: Where the Short's own PICK A COLOR plate lands in the 1080x1920 frame, as
#: `(left, top, right, bottom)` in pixels.
#:
#: Read off `sloped.overlays`, not measured off a delivered file, so the
#: contrast number below is about the picture the card will sit on rather than
#: about a card that happens to have been rendered. See `hook_contrast`.
HOOK_BOX = (86, 1418, 994, 1652)


#: Frame pairs the parallax test is taken across, as `(label, before, after)`
#: in output seconds. A quarter of a second is fifteen frames: long enough for
#: a far band to move a measurable number of pixels, short enough that the two
#: images still have the same content for the matcher to lock onto.
#:
#: Five moves, chosen for what the camera does rather than for what the race
#: does - a parallax test on a static camera measures nothing.
#: A tenth of a second - six frames - rather than V25's quarter.
#:
#: V25 tracked a rock world whose nearest band was eighty units out and picked
#: an interval long enough for the far ranges to move a measurable amount. A
#: contained stage puts its near wall at thirty to sixty units from the lens,
#: and over a quarter second the near band leaves the block matcher's own
#: search window: the first run of this reported 85.6 px against a search of
#: 72, which is not a measurement, it is a number pressed against a wall.
PARALLAX_PAIRS: tuple[tuple[str, float, float], ...] = (
    ("descent_run", 5.000, 5.100),
    ("obstacle_pan", 9.500, 9.600),
    ("fork_swing", 12.300, 12.400),
    ("branch_cross", 14.000, 14.100),
    ("final_dive", 16.400, 16.500),
)


#: Distances from the lens, in layout units, that the parallax curve is
#: reported at. They bracket what a contained stage puts where: structure at
#: 20 to 60, the deck band at 60 to 120, the wall at 90 to 200.
PARALLAX_DISTANCES: tuple[float, ...] = (20.0, 40.0, 80.0, 160.0, 320.0)


def parallax_curve(before: Sequence[float], after: Sequence[float],
                   distances: Sequence[float] = PARALLAX_DISTANCES,
                   ) -> dict[str, float]:
    """Screen travel of a *static* world point, by its distance from the lens.

    Exact, and it needs no render: two solved camera poses and one point. The
    point is placed on the first pose's own view axis at each distance, and the
    displacement is where the second pose puts it.

    **This is the parallax the camera move makes available**, and it is a
    property of the camera track rather than of any world - identical for all
    four of them. A world converts it into depth by having something at more
    than one distance; a world with everything at one distance gets one speed
    however much the camera moves, which is the wallpaper failure this whole
    section exists to rule out.

    The split between the two terms is worth keeping in mind when reading the
    numbers: a camera *rotation* moves everything by the same angle whatever
    its distance, and only the *translation* term falls off with depth. So the
    curve flattens as a move becomes more of a pan and less of a dolly, and a
    flat curve means the shot had no parallax to give rather than that the
    world failed to show any.
    """
    from sloped.presentation import project

    camera_a = (before[1], before[2], before[3])
    aim_a = (before[4], before[5], before[6])
    camera_b = (after[1], after[2], after[3])
    aim_b = (after[4], after[5], after[6])
    forward = [aim_a[i] - camera_a[i] for i in range(3)]
    reach = math.sqrt(sum(v * v for v in forward)) or 1.0
    forward = [v / reach for v in forward]
    out: dict[str, float] = {}
    for distance in distances:
        point = [camera_a[i] + forward[i] * distance for i in range(3)]
        first = project(camera_a, aim_a, float(before[7]), point, WIDTH, HEIGHT)
        second = project(camera_b, aim_b, float(after[7]), point, WIDTH, HEIGHT)
        if first is None or second is None:
            continue
        out["%.0f" % distance] = round(
            math.hypot(second[0] - first[0], second[1] - first[1]), 2)
    return out


def mask_travel(before: dict[str, Any], after: dict[str, Any],
                band: str) -> dict[str, float] | None:
    """How much of a band's screen area is the *same* area a moment later.

    The complement of a displacement, and the one pixel measurement of motion
    that survives this project's own look. Both worlds here are flat-shaded by
    design - V26's stylised rock has an L* standard deviation of 0.1 to 0.5
    across a 41-pixel window, and a graphite wall panel has less - so a block
    matcher has nothing to lock onto in either of them and reports a
    displacement for one or two bands out of three. Overlap needs no texture:
    it asks how far a *silhouette* moved, which is the thing a viewer reads
    parallax from anyway.

    Its weakness is the one V25 named when it rejected mask correlation: a
    band's mask changes shape because something moved in front of it as well as
    because it moved. Over a tenth of a second on this camera track that second
    term is small, and `cover` is reported beside it so a band that is being
    eaten rather than moved can be seen doing it.
    """
    import numpy as np

    a = before.get(band)
    b = after.get(band)
    if a is None or b is None:
        return None
    # **Two per cent of the frame, and the floor had to be raised to it.**
    # At a fifth of one per cent the V26 control's own wall band - a sliver
    # along one edge in three of the five moves - reported `moved` of 0.99,
    # because a sliver that the machine eats and uncovers changes almost all
    # of its own area without going anywhere. A band has to be a real area of
    # the picture before an overlap says anything about motion.
    floor = 0.02 * a.size
    if int(a.sum()) < floor or int(b.sum()) < floor:
        return None
    union = int((a | b).sum())
    if union == 0:
        return None
    overlap = int((a & b).sum())
    return {
        "iou": round(overlap / union, 4),
        "moved": round(1.0 - overlap / union, 4),
        "cover_before": round(float(a.mean()), 4),
        "cover_after": round(float(b.mean()), 4),
    }


@dataclass(frozen=True)
class Clip:
    """One motion proof: a window of the film, rendered whole."""

    key: str
    title: str
    start: float
    end: float


CLIPS: tuple[Clip, ...] = (
    Clip("opening", "the first five seconds", 0.000, 5.000),
    Clip("middle", "descent to merge", 5.000, 15.567),
    Clip("finish", "the final cut and the payoff", 15.567, 20.117),
)


def clip(key: str) -> Clip:
    for entry in CLIPS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V27 clip named {key!r}")


# --- the depth bands --------------------------------------------------------


@dataclass(frozen=True)
class Layer:
    """One depth band, its marker hue, and roughly where it stands."""

    key: str
    title: str
    hue: tuple[int, int, int]
    order: int
    about: str
    ranked: bool = True


#: Four bands, and the count is forced rather than chosen: a parallax test
#: needs at least three depths to have an ordering to check, and a fourth that
#: is not at *a* depth - the heightfield, which spans five to ninety-five units
#: from the lens - has to be measured and excluded from the ranking. Exactly
#: V25's arrangement with different objects in it.
LAYERS: tuple[Layer, ...] = (
    Layer("terrain", "near ground", (255, 60, 120), 0,
          "the heightfield the course is cut into; unchanged from V26 and "
          "only repainted", ranked=False),
    Layer("structure", "stage structure", (255, 0, 200), 1,
          "columns, bays and overhead members: 30-90 units, the band that "
          "carries the parallax"),
    Layer("deck", "deck bands", (255, 120, 0), 2,
          "the floor plates beyond the landform, 76-150"),
    Layer("shell", "enclosure wall", (0, 230, 160), 3,
          "the wall itself, 88-150"),
)

#: Which palette keys each band is painted from in the marker profiles.
#:
#: **Disjoint, and one surface may not belong to two bands.** V25.2 found this
#: the expensive way: it painted the obstacle's two ground zones with rock keys
#: that `MARKED` files under midground, and the measured world cover at the
#: obstacle went from 12.5% to 39.3% without a single object being added. So
#: `hall_trim` is the shell's cornice and plinth and *only* that - a pylon cap
#: is `hall_rib` in all three profiles, and the test below enforces it.
MARKED: dict[str, tuple[str, ...]] = {
    "terrain": ("slope_cliff", "slope_rock", "slope_earth", "slope_scree",
                "slope_cap", "slope_boulder"),
    "structure": ("hall_rib", "hall_grate", "hall_beam"),
    "deck": ("hall_deck", "hall_deck_dark"),
    "shell": ("hall_panel", "hall_panel_dark", "hall_glass", "hall_trim"),
}

#: The control's bands, in V27's own hues, so a V26 frame can be segmented on
#: the same four-colour scale a contained frame is. V25's seven bands collapse
#: onto these four by what they *do* in the picture rather than by what they
#: are made of: the near ground is the near ground, foreground rock and
#: vegetation are the structure band, the ridges and the ravine floor are the
#: deck band, and the valley walls and distant ranges are the shell band.
MARKED_CONTROL: dict[str, tuple[str, ...]] = {
    "terrain": ("slope_cliff", "slope_rock", "slope_earth", "slope_scree",
                "slope_cap", "slope_boulder"),
    "structure": ("world_rock", "world_scarp", "world_soil", "world_deck",
                  "world_deck_dark", "conifer_deep", "conifer_dark",
                  "world_shrub", "world_warm_rock", "world_ember",
                  "world_pocket", "world_pocket_floor", "world_pocket_grit",
                  "world_gravel", "world_bench", "world_concrete"),
    "deck": ("world_cliff_face", "world_cliff_ledge", "world_water",
             "world_wet", "world_damp"),
    "shell": ("world_wall_face", "world_wall_ledge", "rock_soft_near",
              "rock_soft_mid", "rock_soft_far", "rock_soft_haze",
              "far_structure"),
}


def layer(key: str) -> Layer:
    for entry in LAYERS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V27 layer named {key!r}")


def marked_for(profile: str) -> dict[str, tuple[str, ...]]:
    return MARKED_CONTROL if profile == CONTROL.key else MARKED


# --- segmentation, on V27's four bands --------------------------------------


def _hues() -> tuple[list[str], Any]:
    import numpy as np

    keys = [one.key for one in LAYERS]
    return keys, np.array([one.hue for one in LAYERS], dtype=float)


def segment(pixels, world_pixels=None) -> dict[str, Any]:
    """Split a marker render into one boolean mask per band.

    Nearest-hue among :data:`LAYERS` with a chroma floor, and - when a
    world-only pass is supplied - a pixel counts only where the two agree.
    That second half is what subtracts the machine, and V25 found out the hard
    way what happens without it: the V23 baseline, which has no foreground rock
    in it at all, measured as 22% foreground rock. The near ground had drifted
    one band over.
    """
    import numpy as np

    keys, hues = _hues()
    flat = pixels.reshape(-1, 3).astype(float)
    chroma = flat.max(axis=1) - flat.min(axis=1)
    distance = np.linalg.norm(flat[:, None, :] - hues[None, :, :], axis=2)
    nearest = distance.argmin(axis=1)
    live = chroma >= CHROMA_FLOOR
    masks: dict[str, Any] = {}
    for index, key in enumerate(keys):
        masks[key] = ((nearest == index) & live).reshape(pixels.shape[:2])
    if world_pixels is not None:
        other = segment(world_pixels)
        for key in keys:
            masks[key] = masks[key] & other[key]
    return masks


def layer_cover(masks: dict[str, Any]) -> dict[str, float]:
    return {key: float(mask.mean()) for key, mask in masks.items()}


def layer_value(pixels, masks: dict[str, Any],
                floor: int = 400) -> dict[str, float]:
    """Mean luma per band, off the *lit* render rather than the marker."""
    import numpy as np

    grey = (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2])
    out: dict[str, float] = {}
    for key, mask in masks.items():
        if int(mask.sum()) < floor:
            continue
        out[key] = float(grey[mask].mean())
    return out


def recession(values: dict[str, float]) -> list[tuple[str, str, float]]:
    """Each adjacent ranked pair's value step, nearest band first.

    A world with depth gets darker or lighter monotonically outward; one that
    does not is a set of cut-outs at one value, whatever its geometry says.
    """
    ranked = [one for one in LAYERS if one.ranked and one.key in values]
    ranked.sort(key=lambda one: one.order)
    out: list[tuple[str, str, float]] = []
    for index in range(len(ranked) - 1):
        near, far = ranked[index], ranked[index + 1]
        out.append((near.key, far.key, values[far.key] - values[near.key]))
    return out


# --- the camera envelope ----------------------------------------------------


def frames_of(track: dict[str, Any]) -> list[list[float]]:
    """Every frame of a solved track, as `[t, px, py, pz, ax, ay, az, fov]`."""
    return [frame for cut in track["cuts"] for frame in cut["frames"]]


def _frustum(frame: Sequence[float]) -> tuple[float, ...]:
    px, py, pz, ax, ay, az, fov = frame[1:8]
    reach = math.hypot(ax - px, az - pz)
    yaw = math.atan2(ax - px, az - pz)
    down = math.atan2(-(ay - py), reach) if reach > 1e-9 else math.pi / 2.0
    half_v = math.radians(fov) / 2.0
    half_h = math.atan(math.tan(half_v) * WIDTH / HEIGHT)
    return px, py, pz, yaw, down, half_v, half_h


def visible_ceiling(frames: Iterable[Sequence[float]], x: float,
                    z: float) -> float | None:
    """The highest `y` at plan `(x, z)` inside any frame's frustum.

    `None` means the column is outside every frame - a place the film never
    photographs, where a form is a triangle budget and nothing else.

    The frustum is treated as the four planes of a perspective camera, so the
    height returned is the top *edge* of the picture at that column's own
    forward distance, not the top of a cone. That distinction is worth two
    units at the frame corners and it is the difference between a wall that
    tops out in shot and one that tops out just above it.
    """
    best: float | None = None
    for frame in frames:
        px, py, pz, yaw, down, half_v, half_h = _frustum(frame)
        dx, dz = x - px, z - pz
        reach = math.hypot(dx, dz)
        if reach < 1e-6:
            continue
        offset = (math.atan2(dx, dz) - yaw + math.pi) % (2.0 * math.pi) - math.pi
        if abs(offset) > half_h:
            continue
        forward = reach * math.cos(offset)
        y = py - forward * math.tan(down - half_v)
        if best is None or y > best:
            best = y
    return best


def ceiling_grid(frames: Sequence[Sequence[float]],
                 radii: Sequence[float] = (30.0, 50.0, 70.0, 90.0, 110.0,
                                           130.0, 160.0),
                 step: float = 15.0) -> dict[str, Any]:
    """The visible ceiling over a polar grid about :data:`CENTRE`.

    The table `--stage envelope` prints, and the evidence behind both of the
    placement rules in the docs.
    """
    rows: list[dict[str, Any]] = []
    seen: set[float] = set()
    for radius in radii:
        cells: dict[float, float | None] = {}
        bearing = 0.0
        while bearing < 360.0:
            angle = math.radians(bearing)
            x = CENTRE[0] + math.sin(angle) * radius
            z = CENTRE[1] + math.cos(angle) * radius
            value = visible_ceiling(frames, x, z)
            cells[bearing] = value
            if value is not None:
                seen.add(bearing)
            bearing += step
        rows.append({"radius": radius, "cells": cells})
    return {"rows": rows, "bearings_seen": sorted(seen), "step": step}


def unseen_arc(grid: dict[str, Any]) -> list[tuple[float, float]]:
    """Bearing ranges that never appear in any frame, as `(from, to)`."""
    step = float(grid["step"])
    seen = set(grid["bearings_seen"])
    out: list[tuple[float, float]] = []
    run: float | None = None
    bearing = 0.0
    while bearing < 360.0:
        if bearing not in seen:
            if run is None:
                run = bearing
        elif run is not None:
            out.append((run, bearing))
            run = None
        bearing += step
    if run is not None:
        out.append((run, 360.0))
    return out


# --- scoring ----------------------------------------------------------------

#: The brief's Part Y, as the twelve rows the recommendation is argued on.
#: Scores are the author's, out of five, and the point of writing them down is
#: that a reader can disagree with one row rather than with a paragraph.
CRITERIA: tuple[tuple[str, str], ...] = (
    ("racer_focus", "do the eight marbles stay the first thing read"),
    ("machine_focus", "does the machine stay the second"),
    ("hook", "frame 0: racers, PICK A COLOR, START, no tangency"),
    ("depth", "foreground, midground and background all present"),
    ("parallax", "three separable speeds during a camera move"),
    ("premium", "does it look expensive"),
    ("cleanliness", "is the background quiet behind the track"),
    ("reuse", "would it host a different course"),
    ("skins", "would it host country flags and other racer palettes"),
    ("layouts", "would it host a different machine footprint"),
    ("finish", "is the payoff a place"),
    ("cost", "meshes, triangles and milliseconds against V26"),
)


def score_table(scores: dict[str, dict[str, int]]) -> str:
    rows: list[dict[str, Any]] = []
    for key, label in CRITERIA:
        row: dict[str, Any] = {"criterion": label}
        for entry in ALL:
            row[entry.tag] = scores.get(entry.tag, {}).get(key, "-")
        rows.append(row)
    totals: dict[str, Any] = {"criterion": "TOTAL (60)"}
    for entry in ALL:
        values = [scores.get(entry.tag, {}).get(key) for key, _ in CRITERIA]
        kept = [one for one in values if isinstance(one, int)]
        totals[entry.tag] = sum(kept) if kept else "-"
    rows.append(totals)
    return table(rows, ["criterion"] + [one.tag for one in ALL])


# --- small helpers ----------------------------------------------------------


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")

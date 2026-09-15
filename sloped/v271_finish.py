"""V27.1: the finish correction, and the instrument that found what was wrong.

V27 recommended concept A, `contained_hall`, at 55 of 60, and left one number
open in its §19: the machine-to-background separation at the winner crossing
fell from V26's 90 luma to 49, and at the payoff from 84 to 53. That is a
regression in the shot the film is built around, and this pass exists to close
it.

It closes in two pieces, and the first one is not a render change.

## 1  Most of the drop was the ruler, not the room

`v27_contained.segment` splits a marker render into four depth bands by nearest
hue, and subtracts the machine by requiring that the **whole** marker pass and
the **world-only** marker pass agree at a pixel. The intent is exact: a pixel
the machine covers shows the machine in one pass and the world in the other, so
the two disagree and the pixel is dropped.

The intent fails when the machine's own colour happens to land in the same
nearest-hue bucket as the world behind it. The finish chute is warm cream, and
cream's nearest neighbour among V27's four band hues is `terrain`'s rose
(255, 60, 120) - not because cream is pink, but because rose is the least
distant of four saturated hues none of which is cream. So:

    in `contained_hall`   the chute stands over the repainted landform, which
                          is rose. Both passes say "terrain". The brightest
                          machine surface in the frame is counted as
                          background - and removed from the machine.

    in `aurora_valley_v26` the same chute stands over V26's near-field rock,
                          which the control marker paints magenta. The passes
                          disagree, and the chute is correctly discarded.

The comparison was therefore not like for like, and it was asymmetric in the
direction that flatters V26. :func:`machine_mask` replaces the agreement test
with an **occlusion** test - a pixel is machine where removing the machine
changes it - which is what the agreement test was an approximation of. Every
marker material is `unshaded` and `no_fog`, so a world pixel is a constant flat
colour between the two passes and the difference is the machine and nothing
else. The threshold sits on a plateau: at the winner, `contained_hall`'s
machine cover is 47.8% at a threshold of 12, 46.8% at 24 and 46.4% at 48.

Re-measured through it, at the same frames, from the same files:

                        V26      V27 hall    what V27 reported
    winner crossing    90.9        96.4        90 -> 49
    payoff             85.3       100.1        84 -> 53
    final approach    128.4       112.0         -

Two of the three finish moments were never behind V26. One was.

## 2  What was really wrong: one slab

The final approach is a real loss and :mod:`tools.sloped_v271_finish`'s surface
probe names the cause without a guess. `hall_deck` covers 28.6% of that frame
at luma 51, against V26's 20-luma ravine floor - and 27.8 of those 28.6 points
are a single object, the **finish bay's own landing pad**, the 40x34 slab
`contained_hall` lays under the line to give the finish a place to stand.

`contained_hall_v271` is that slab in `hall_deck_dark` instead of `hall_deck`.
One field. It is the brief's own first-choice fix - a darker background
directly behind FINISH - it adds no geometry, names no new material key, and
leaves every other surface in the hall exactly where V27 put it.

**It is not confined to three frames, and it cannot be.** The pad is behind the
finish, and eight of the twelve moments can see some of it: the merge shot's
own description in `v27_contained.MOMENTS` is "the routes rejoining, with the
finish already in frame". So the delta reaches the obstacle, the fork approach,
the split, the branch, the merge and the three finish moments, and improves
every one of them - +9.2 luma at the final approach, +2.4 at the merge, +2.6 at
the winner, nothing worse anywhere. The other four are byte-identical.

## 3  What this module does not do

It does not rewrite :mod:`sloped.v27_contained`. Every number V27 published
stays reproducible from the code that published it - `contained_hall` is
untouched, its four markers are untouched, and `tests/test_sloped_v271_contained.py`
renders a V27 frame and checks its hash. The corrected instrument lives here,
beside the old one, and the report quotes both.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sloped import v27_contained as v27
from sloped.v27_contained import (  # noqa: F401  (re-exported: V27's frames)
    CENTRE,
    FPS,
    HEIGHT,
    MOMENTS,
    SEED,
    WIDTH,
    frames_of,
    moment,
    seconds,
    segment,
    write_json,
)

__all__ = [
    "BAND_HUES",
    "CONTROL",
    "DIFF_FLOOR",
    "FINISH",
    "FLAG",
    "FLAG_MOMENTS",
    "FLAG_RACER",
    "PARENT",
    "PROFILE",
    "SURFACES",
    "TARGET",
    "background_mask",
    "collar",
    "collar_pair",
    "luma",
    "machine_mask",
    "separation",
    "surface_masks",
    "verdict",
]

#: The profile this pass produces, and the two it is measured against.
#:
#: `contained_hall` is **not** overwritten: V27's proofs have to stay
#: reproducible, and a lab that edits the thing it is comparing against has
#: measured nothing.
PROFILE = "contained_hall_v271"
PARENT = "contained_hall"
CONTROL = "aurora_valley_v26"

#: The marker over the corrected profile. It has to exist separately from
#: `_marker_v27a` for one reason only - a marker inherits its parent's world,
#: and the corrected profile's world differs by the pad's material - and the
#: band it files that material under is the same either way, so the two markers
#: are in fact identical renders. Generated rather than aliased, because an
#: alias is a claim and a render is a proof.
MARKER = "_marker_v271"

#: The surface probe: every hall material its own flat hue, so a bright area in
#: a finish frame can be *named* rather than attributed.
#:
#: **The machine is masked out before this is read, and that is not optional.**
#: The first version of this probe painted `hall_trim` white, found 2 to 8 per
#: cent of every frame at luma 245, and concluded the cornice was clipping. It
#: was not: white is the machine's own pearl and the finish chute's cream, and
#: the classifier had been handed the one hue the machine also wears. Nothing
#: in the hall clips at any moment. See the report's §4.
SURFACES: dict[str, str] = {
    "hall_deck": "#FF2000",
    "hall_deck_dark": "#FF9000",
    "hall_panel": "#00FF40",
    "hall_panel_dark": "#0060FF",
    "hall_trim": "#00FFFF",
    "hall_rib": "#FF00FF",
    "hall_beam": "#FFFF00",
    "hall_glass": "#8000FF",
}

#: The two practicals. They carry their colour in `emission`, so an `albedo`
#: row would not move them and the probe recolours the emission instead.
SURFACE_LIGHTS: dict[str, str] = {
    "lit_hall_warm": "#FF0080",
    "lit_hall_cool": "#80FF00",
}

#: The landform, flat and dark, so it is one region in the probe rather than
#: eleven. `vertex_tint` is left on - it is what the course terrain shades
#: with - so this reads as a range rather than a value, which is why the probe
#: is used for *where* and the marker for *how much*.
SURFACE_GROUND = "#303030"

#: The three shots the pass is judged on, in the order the film plays them.
FINISH: tuple[str, ...] = ("final_approach", "winner", "payoff")

#: The brief's bar for machine-to-background separation at the finish, in luma.
TARGET = 70.0

#: The five finish frames the brief asks the three worlds to be compared at, as
#: **output** seconds on V24's edit.
#:
#: Three of them are V27 moments and two are not, and the two that are not are
#: why this list exists rather than a slice of `FINISH`:
#:
#: * **the ring.** V24 opens the WINNER mark on the crossing and runs it
#:   `v24_payoff.RING_SECONDS` = 0.300 s, so the mark is up from 17.517 to
#:   17.817 and the middle of it is the frame that shows the ring *and* the
#:   marble. `v24_payoff` measured the marble's own visibility at 0.217 s of
#:   that 0.300, which is why the ring opens on the crossing rather than after
#:   it, and why this sample is at the middle and not the end.
#: * **the final frame.** 20.117 s is the film's own duration - the track says
#:   so - and the last frame of it is one frame earlier.
#:
#: They are rendered as their own `--at` list, and compared only against each
#: other, for the reason V27 found: a still is reproducible against another
#: still asked for in the same list and against no other.
PROOF_FRAMES: tuple[tuple[str, float, str], ...] = (
    ("final_approach", 16.467, "1  Final approach"),
    ("winner", 17.517, "2  Winner crossing"),
    ("ring", 17.667, "3  The WINNER ring"),
    ("payoff", 18.500, "4  Payoff"),
    ("final_frame", 20.100, "5  Final frame"),
)

#: The marker band hues, for `surface_masks`' companion.
BAND_HUES = {one.key: one.hue for one in v27.LAYERS}


# --- the corrected instrument -----------------------------------------------

#: How far a pixel has to move between the two marker passes to count as
#: machine, as a max-channel difference in 0-255.
#:
#: Chosen off the histogram rather than by taste, and the histogram is flat
#: where it matters: over `contained_hall`'s winner frame the machine cover is
#: 49.9% at a floor of 4, 47.8% at 12, 46.8% at 24 and 46.4% at 48. Anything
#: from about 10 to about 60 gives the same mask to within 1.4 of a per cent,
#: because the two populations it separates are "unchanged flat colour" and
#: "a different object entirely". 24 is the middle of that plateau.
DIFF_FLOOR = 24.0


def luma(pixels) -> Any:
    """Rec. 709 luma of an RGB array, in 0-255. V27's own, restated once."""
    return (0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1]
            + 0.0722 * pixels[..., 2])


def machine_mask(whole, world, floor: float = DIFF_FLOOR):
    """Where the machine is, by occlusion rather than by colour.

    `whole` is the marker profile rendered normally; `world` is the same
    profile rendered with `--layers=world`, which culls the machine. A pixel
    carries machine exactly where hiding the machine changes it.

    **Why this and not `--layers=machine`.** The machine layer photographs the
    machine with the world culled, so it returns the machine's *whole*
    silhouette including the parts the world stands in front of - and in V26 a
    great deal of machine stands behind foreground rock. A screen-space mask
    has to be what is visible, not what exists.

    **Why it is exact here and would not be on a lit render.** Every material a
    marker profile paints is `unshaded` and `no_fog`, so a world surface is the
    same constant colour in both passes: it carries no shading to change, takes
    no shadow from the machine that was removed, and picks up no fog. The only
    thing that can differ between the two images is which object a pixel is.
    """
    import numpy as np

    return np.abs(whole.astype(float) - world.astype(float)).max(axis=2) > floor


def background_mask(whole, world, floor: float = DIFF_FLOOR):
    """The four depth bands, with the machine taken out of them.

    V27's segmentation is kept for *which band* a world pixel belongs to - it
    is a good answer to that question and the band hues are far apart - and
    only the machine test is replaced.
    """
    bands = v27.segment(whole, world)
    machine = machine_mask(whole, world, floor)
    return {key: mask & ~machine for key, mask in bands.items()}, machine


def separation(pixels, machine, background) -> float | None:
    """Mean-luma difference between the machine and the world behind it.

    The brief's number. `None` where either population is too small to have a
    mean worth quoting.
    """
    if int(machine.sum()) < 200 or int(background.sum()) < 200:
        return None
    grey = luma(pixels)
    return round(float(grey[machine].mean() - grey[background].mean()), 2)


def _dilate(mask, radius: int):
    from PIL import Image, ImageFilter
    import numpy as np

    plate = Image.fromarray((mask * 255).astype(np.uint8))
    return np.asarray(plate.filter(ImageFilter.MaxFilter(2 * radius + 1))) > 127


def _erode(mask, radius: int):
    from PIL import Image, ImageFilter
    import numpy as np

    plate = Image.fromarray((mask * 255).astype(np.uint8))
    return np.asarray(plate.filter(ImageFilter.MinFilter(2 * radius + 1))) > 127


def collar(pixels, machine, background, reach: int = 12,
           lip: int = 6) -> float | None:
    """Separation measured **at the silhouette** rather than over the frame.

    A frame mean can be right while the picture is wrong: a machine that is
    120 luma above the average of everything behind it can still meet its
    background at the one place the eye reads an edge. This takes the outer
    `lip` pixels of the machine against the `reach` pixels of world outside it.

    Reported beside the global number, never instead of it.
    """
    import numpy as np

    ring = _dilate(machine, reach) & background
    edge = machine & ~_erode(machine, lip)
    if int(ring.sum()) < 500 or int(edge.sum()) < 500:
        return None
    grey = luma(pixels)
    return round(float(grey[edge].mean() - grey[ring].mean()), 2)


def collar_pair(pixels_a, machine_a, background_a,
                pixels_b, machine_b, background_b,
                reach: int = 12, lip: int = 6) -> tuple[float | None, float | None]:
    """Two worlds' collar separation, on the machine **both** of them show.

    **The correction this exists for.** Measured on its own silhouette, a
    contained frame scores worse at the collar than V26 does - 50.8 against
    78.7 at the winner - and the difference is not contrast. It is coverage:
    V26's foreground rock stands in front of the machine and hides 4 per cent
    of the frame's worth of it, and the machine it hides is the far, dark,
    lower edge. Take that away and V26's remaining silhouette is its bright
    half, while the hall's is all of it.

    Intersecting the two masks asks both worlds about the same object. On that
    footing the hall wins at both payoff moments - 88.9 against 78.7 at the
    winner, 90.6 against 64.1 at the payoff - which is the opposite of the
    verdict the uncorrected pairing gives.
    """
    import numpy as np

    common = machine_a & machine_b
    if int(common.sum()) < 2000:
        return None, None
    edge = common & ~_erode(common, lip)
    out: list[float | None] = []
    for pixels, background in ((pixels_a, background_a), (pixels_b, background_b)):
        ring = _dilate(common, reach) & background & ~common
        if int(ring.sum()) < 500 or int(edge.sum()) < 500:
            out.append(None)
            continue
        grey = luma(pixels)
        out.append(round(float(grey[edge].mean() - grey[ring].mean()), 2))
    return out[0], out[1]


def surface_masks(probe, machine) -> dict[str, Any]:
    """One boolean mask per hall material, off a probe render.

    `machine` is passed in and subtracted rather than inferred, for the reason
    :data:`SURFACES` gives: a probe hue and a machine colour can collide, and a
    classifier that is not told where the machine is will hand back the
    machine's own pearl as a wall.
    """
    import numpy as np

    names = list(SURFACES) + list(SURFACE_LIGHTS) + ["ground"]
    hexes = list(SURFACES.values()) + list(SURFACE_LIGHTS.values()) + [SURFACE_GROUND]
    table = np.array([[int(one[i:i + 2], 16) for i in (1, 3, 5)]
                      for one in hexes], dtype=float)
    flat = probe.reshape(-1, 3).astype(float)
    distance = np.linalg.norm(flat[:, None, :] - table[None, :, :], axis=2)
    nearest = distance.argmin(axis=1)
    close = distance.min(axis=1) < 40.0
    out: dict[str, Any] = {}
    for index, name in enumerate(names):
        mask = ((nearest == index) & close).reshape(probe.shape[:2])
        out[name] = mask & ~machine
    return out


def verdict(before: float | None, after: float | None,
            control: float | None) -> str:
    """One line per finish moment, for the report."""
    if after is None:
        return "not measurable"
    tail = "" if control is None else f", V26 {control:.1f}"
    if before is None:
        return f"{after:.1f}{tail}"
    return f"{before:.1f} -> {after:.1f}{tail}"


# --- the country-skin probe -------------------------------------------------


@dataclass(frozen=True)
class Flag:
    """One flag, as bands about a tilted axis plus one emblem.

    `key` is the **appearance name Godot knows**, not a country code: it is
    what `--racers=` is handed and what `racer_visual.FLAGS` is keyed by, and
    `tests/test_sloped_v271_contained.py` checks the two agree. The first
    version of this held "india" here, the scene did not recognise it, and
    `sloped_race_scene` fell back to its default appearance and rendered five
    sheets of plain marbles that the probe then scored - a silent fallback that
    produced a finished-looking table of wrong numbers. `_render_at` now fails
    on that push_error rather than photographing it.

    Not a texture file and not a decal. `racer_visual.gd` already bakes its
    marker into the racer's own albedo map in the mesh's UV space, which is
    why a marker turns with the replay quaternion and cannot be faked; a flag
    is the same mechanism with the base colour moved into the map, exactly as
    that file's own docstring predicted. So this is four colours and two axes,
    and the renderer builds the image.
    """

    key: str
    title: str
    bands: tuple[str, ...]
    emblem: str
    emblem_band: int


#: India, and the choice is a test rather than a preference.
#:
#: The brief asks for a flag with several strong colours. This one has three,
#: one of which is **white** - the value a graphite hall has least of and the
#: value a cream track has most of, so it asks the two questions that matter at
#: once: does a flag stay a flag against the wall, and does it stay separate
#: from the chute. It also carries a fine navy wheel on the white band, which
#: is the smallest thing any skin in this family would ever have to hold at
#: 270 px wide.
FLAG = Flag(
    key="flag_in",
    title="India",
    bands=("#FF9933", "#FFFFFF", "#138808"),
    emblem="#000080",
    emblem_band=1,
)

#: Which racer wears it. The winner, so Part B and Part E are the same render:
#: if the flag is readable it is readable *as the payoff*, and if the ring
#: still points at it the ring is checked under the skin it would ship with.
FLAG_RACER = 5

#: Where the probe is taken. Frame 0 and the finish are the brief's; the mixer,
#: the obstacle and the fork are the three places the marble is turning fastest
#: and smallest, which is where a flag either survives or smears.
FLAG_MOMENTS: tuple[str, ...] = ("frame0", "mixer", "obstacle",
                                 "fork_approach", "winner")


def flag_axes() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The band axis and the emblem axis, in the marble's own frame.

    **Deliberately not axis-aligned**, for the reason `racer_visual` gives
    about its own marker normals: a marble is dropped with an identity
    orientation, so bands about local +Y would start as a horizontal tricolour
    on the line and read as a sticker rather than as a body. They are also not
    parallel to each other, so no single rotation holds both the bands and the
    wheel still.
    """
    band = (-0.52, 0.30, 0.80)
    emblem = (0.6465, 0.7508, 0.1356)
    return band, emblem


def band_edges() -> tuple[float, float]:
    """Where the three zones meet, as `dot(point, axis)`.

    At +-1/3 rather than at +-0.5: the area of a spherical zone is
    proportional to its height, so thirds of the *axis* are thirds of the
    *surface*, and a flag whose stripes are equal by area is the one that still
    reads as a tricolour when the marble is seen edge on.
    """
    return -1.0 / 3.0, 1.0 / 3.0


# --- the surviving V27 tables, restated for the report ----------------------


#: What V27 published for the finish, so the report can put the two side by
#: side without the reader having to open the old document.
V27_REPORTED = {
    "winner": {"v26": 90.0, "hall": 49.0},
    "payoff": {"v26": 84.0, "hall": 53.0},
}


def polar(bearing: float, radius: float,
          centre: tuple[float, float] = CENTRE) -> tuple[float, float]:
    """`environment_stage._polar`, in Python, for the sector survey."""
    angle = math.radians(bearing)
    return (centre[0] + math.sin(angle) * radius,
            centre[1] + math.cos(angle) * radius)


def frame_at(frames: Sequence[Sequence[float]], second: float) -> Sequence[float]:
    """The solved camera frame nearest an output second."""
    return min(frames, key=lambda one: abs(one[0] - second))


def in_frame(frame: Sequence[float], point: tuple[float, float, float],
             margin: int = 60) -> tuple[float, float] | None:
    """Where a world point lands in the 1080x1920 picture, or `None`.

    Uses the film's own projector - `sloped.presentation.project` - rather than
    a frustum test, because the question the sector survey asks is "is this
    segment in shot", and a frustum test answers "is its centre inside four
    planes", which is the same thing only for a point.
    """
    from sloped.presentation import project

    camera = (frame[1], frame[2], frame[3])
    aim = (frame[4], frame[5], frame[6])
    got = project(camera, aim, float(frame[7]), point, WIDTH, HEIGHT)
    if got is None:
        return None
    x, y = got[0], got[1]
    if -margin <= x <= WIDTH + margin and -margin <= y <= HEIGHT + margin:
        return (x, y)
    return None

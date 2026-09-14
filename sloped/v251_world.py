"""V25.1: what the world-art pass renders, compares and measures.

The lab's own table of facts, alongside `sloped/v25_world.py` rather than
replacing it. V25's moments, clips, crops, depth bands and measurement code
are all reused unchanged - **the control is V25 B and a control has to be
measured by the instrument that measured it**, or a difference in the sheet
could be a difference in the ruler.

What is new here is only what V25.1 adds:

  * one more variant, `aurora_valley_v251`, and its marker
  * six more world surfaces to put in the segmentation table
  * two more close crops, at the two places the art changed most

Nothing in this module touches the replay, the camera track, the edit or the
seed. Every second named below is an output second on V22.1's own solved
tracks, which is what makes a V25 B frame and a V25.1 frame the same frame of
the same race.
"""

from __future__ import annotations

from sloped import v25_world
from sloped.v25_world import (  # noqa: F401  (re-exported: one lab, one table)
    CHROMA_FLOOR,
    CLIPS,
    COARSE,
    HUE_TOLERANCE,
    MOMENTS,
    PATCH,
    PATCHES,
    PHONE,
    PREVIEW_MOMENTS,
    RACE_MOMENTS,
    SEARCH,
    TEXTURE_FLOOR,
    WIDE,
    Crop,
    Layer,
    Moment,
    Variant,
    band_shift,
    census_of,
    clip,
    layer,
    layer_cover,
    layer_value,
    moment,
    monotone,
    noise,
    parallax,
    parse_cost,
    phone,
    recession,
    seconds_for,
    segment,
    separation,
    table,
    verdict,
)

#: The control. B, exactly as V25 shipped it - not re-rendered from a copy and
#: not re-tuned. The brief locks B's density and layout as the target, so the
#: comparison this lab exists to make is B against V25.1 at identical frames.
CONTROL = Variant(
    "aurora_valley_v25b", "V25 B (control)",
    "the recommended V25 world: the same layout and density, built from "
    "`smooth_mass` and rounded boxes",
)

CANDIDATE = Variant(
    "aurora_valley_v251", "V25.1 - world art",
    "B's layout and density from a faceted rock kit and a tiered vegetation "
    "kit, with material zones, cut benches, five distinct landmarks and a "
    "finish basin",
)

ALL: tuple[Variant, ...] = (CONTROL, CANDIDATE)

MARKERS: dict[str, str] = {
    CONTROL.key: "_marker_v25b",
    CANDIDATE.key: "_marker_v251",
}


def marker(key: str) -> str:
    return MARKERS[key]


def variant(key: str) -> Variant:
    for entry in ALL:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25.1 variant named {key!r}")


# --- the depth bands --------------------------------------------------------
#
# V25's seven bands, unchanged, with V25.1's six new surfaces slotted into the
# band each one belongs to. The bands themselves are not renegotiated: a new
# band would mean the control could not be measured on the same axis.

LAYERS: tuple[Layer, ...] = v25_world.LAYERS


def layer_hue(key: str) -> tuple[int, int, int]:
    return layer(key).hue


#: V25's marker table plus the surfaces V25.1 introduces.
#:
#: Which band each new surface joins, and why:
#:
#:   world_concrete   foreground - it is the bench wall, beside the track
#:   world_gravel     terrain    - a material zone *is* the near ground
#:   world_bench      terrain
#:   world_ember      terrain
#:   world_damp       water      - it is the gorge lip and the ravine banks
#:   world_warm_rock  ridges     - the finish basin stands at ridge distance
#:   lit_world_amber  foreground - a practical lens, at foreground range
#:
#: The three zone surfaces count as **terrain** deliberately. A patch is a
#: skin on the heightfield rather than a thing standing on it, so counting it
#: as foreground rock would inflate the one number this lab most wants to be
#: honest about - how much of the frame is world rather than ground.
MARKED: dict[str, tuple[str, ...]] = {
    **{key: tuple(value) for key, value in v25_world.MARKED.items()},
    "terrain": v25_world.MARKED["terrain"] + (
        "world_gravel", "world_bench", "world_ember"),
    "foreground": v25_world.MARKED["foreground"] + (
        "world_concrete", "lit_world_amber"),
    "ridges": v25_world.MARKED["ridges"] + ("world_warm_rock",),
    "water": v25_world.MARKED["water"] + ("world_damp",),
}


# --- the close crops --------------------------------------------------------
#
# V25's seven, plus two the art pass needs and V25 had no reason to cut: the
# start landmark, and the near ground where a material zone meets the bench.

CROPS: tuple[Crop, ...] = v25_world.CROPS + (
    Crop("landmark", "start", (0.0, 0.0, 0.7, 0.42),
         "the shelf above the start, the landmark V25 called correct but not "
         "distinctive"),
    Crop("zones", "descent", (0.0, 0.30, 0.78, 0.86),
         "the near ground on the descent, where the material zones and the "
         "scarps are"),
)


def patch_sites(mask):
    """Where a 41x41 template fits wholly inside a band.

    V25's own site picker, re-exported under a public name because V25.1's
    texture diagnostic needs it and reaching into another module's private
    helper is how two copies of a rule start to drift.
    """
    return v25_world._patch_sites(mask)


def crop(key: str) -> Crop:
    for entry in CROPS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25.1 crop named {key!r}")

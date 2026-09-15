"""V25.2: what the final world-lookdev pass renders, compares and measures.

The lab's own table of facts, alongside `sloped/v25_world.py` and
`sloped/v251_world.py` rather than replacing either. V25's moments, clips,
depth bands and measurement code are reused unchanged, for the reason V25.1
gave and this pass has more need of than V25.1 did: **the control has to be
measured by the instrument that measured it**, or a difference in a sheet is a
difference in the ruler. The control here is V25.1.

What is new is only what V25.2 adds:

  * one more variant, `aurora_valley_v252`, and its marker
  * two more world surfaces to put in the segmentation table
  * five close crops, at the five places the brief asks a question about
  * three measures V25 had no reason to take: the midground dark-pixel
    fraction, the local value spread on a hero rock, and the warm-pixel
    fraction at the finish

Nothing in this module touches the replay, the camera track, the edit or the
seed. Every second named below is an output second on V22.1's own solved
tracks, which is what makes a V25.1 frame and a V25.2 frame the same frame of
the same race.
"""

from __future__ import annotations

import numpy as np

from sloped import v25_world, v251_world
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

#: The control. V25.1, exactly as it shipped - not re-rendered from a copy and
#: not re-tuned. The brief locks V25.1's density, layout, parallax, kit
#: architecture and landmark structure as the target, so the comparison this
#: lab exists to make is V25.1 against V25.2 at identical frames.
CONTROL = v251_world.CANDIDATE

CANDIDATE = Variant(
    "aurora_valley_v252", "V25.2 - final lookdev",
    "V25.1's world and density with the shading response rebuilt: tempered "
    "normals, a baked albedo gradient, a material shadow floor, restrained "
    "warmth, broken hero silhouettes, leaning vegetation, a slate obstacle "
    "pocket and a warm finish basin",
)

ALL: tuple[Variant, ...] = (CONTROL, CANDIDATE)

MARKERS: dict[str, str] = {
    CONTROL.key: "_marker_v251",
    CANDIDATE.key: "_marker_v252",
}


def marker(key: str) -> str:
    return MARKERS[key]


def variant(key: str) -> Variant:
    for entry in ALL:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25.2 variant named {key!r}")


# --- the depth bands --------------------------------------------------------
#
# V25's seven bands, unchanged, with V25.2's two new surfaces slotted into the
# band each belongs to. The bands themselves are not renegotiated: a new band
# would mean the control could not be measured on the same axis.

LAYERS: tuple[Layer, ...] = v25_world.LAYERS


def layer_hue(key: str) -> tuple[int, int, int]:
    return layer(key).hue


#: V25.1's marker table plus the two surfaces V25.2 introduces.
#:
#: `world_pocket` is the obstacle's own stone and joins **ridges**: the east
#: wall stands 54 units out from the obstacle node, which is midground by this
#: lab's own rule of thumb, and putting it in the foreground band would flatter
#: the one number this pass most wants to be honest about.
#:
#: `world_pocket_floor` and `world_pocket_grit` are the *ground* of the same
#: place and join **terrain**, for V25.1's own reason: a zone is a skin on the
#: heightfield rather than a thing standing on it.
#:
#: **They are two keys because of a bug this table caught.** The first build
#: painted those ground zones with the rock key, and the obstacle's measured
#: world cover went from 12.5% to 39.3% - a near-tripling with no object added
#: anywhere, produced entirely by two ground patches being segmented as
#: midground rock. The number was wrong in the flattering direction, which is
#: the direction that does not get questioned.
MARKED: dict[str, tuple[str, ...]] = {
    **{key: tuple(value) for key, value in v251_world.MARKED.items()},
    "ridges": v251_world.MARKED["ridges"] + ("world_pocket",),
    "terrain": v251_world.MARKED["terrain"] + (
        "world_pocket_floor", "world_pocket_grit"),
}


# --- the close crops --------------------------------------------------------
#
# V25.1's nine, plus five the brief names by hand. Each is aimed at one
# question a full 1080x1920 frame shrunk into a sheet cell cannot answer.

CROPS: tuple[Crop, ...] = v251_world.CROPS + (
    Crop("midground", "descent", (0.0, 0.02, 0.42, 0.62),
         "the descent's near cliff mass: one sculpted rock, or twelve dark "
         "polygons"),
    Crop("hero", "obstacle", (0.0, 0.0, 0.52, 0.44),
         "the obstacle's east wall, the pass's one re-composed hero rock"),
    Crop("tree", "finish", (0.24, 0.10, 0.70, 0.42),
         "the stand above the finish basin, at the distance the review "
         "called them teal triangles"),
    Crop("pocket", "obstacle", (0.0, 0.16, 0.66, 0.70),
         "where the obstacle machine meets its own canyon wall"),
    Crop("basin", "finish", (0.0, 0.24, 1.0, 0.78),
         "the two-tier finish basin, warm rim against cold gorge"),
)


def crop(key: str) -> Crop:
    for entry in CROPS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25.2 crop named {key!r}")


def patch_sites(mask):
    """Where a 41x41 template fits wholly inside a band. V25's own picker."""
    return v25_world._patch_sites(mask)


# --- the three measures this pass adds --------------------------------------
#
# The brief asks for these and then, correctly, forbids them from being the
# verdict. They exist to make a claim falsifiable, not to make it: a number
# that moves the right way on a picture that got worse is a number that was
# measuring the wrong thing, and this lab has produced one of those before.

#: Grey level below which a world pixel is "dark" - V25.1's own threshold, so
#: the two passes' dark fractions are the same quantity.
DARK = 12

#: Bands that count as midground for the dark-pixel measure. These are the two
#: the review called a mosaic and the two V25.1 measured getting worse.
MIDGROUND = ("ridges", "walls")


def dark_fraction(grey: "np.ndarray", mask: "np.ndarray") -> float:
    """Share of a band's pixels under `DARK`, in [0, 1].

    `nan` when the band is not on screen, which is different from zero and has
    to stay different: a band with no pixels has no dark pixels, and averaging
    that in as a zero is how a band that vanished looks like a band that got
    brighter.
    """
    total = int(mask.sum())
    if total == 0:
        return float("nan")
    return float((grey[mask] < DARK).sum()) / float(total)


def value_spread(grey: "np.ndarray", mask: "np.ndarray",
                 window: int = 41) -> float:
    """Median local value range over a band, in grey levels.

    **This is the mosaic, as a number.** A faceted mass whose facets differ by
    forty levels and a sculpted mass whose surface turns through ten both have
    the same overall span; what separates them is how much value change there
    is *within a patch the size of one facet*. So this takes V25's own 41x41
    template sites, measures peak-to-trough inside each, and reports the
    median.

    Lower is smoother. It is not "better" without a picture beside it - a band
    driven to zero spread is a flat card - which is why the doc reports it
    against the render rather than instead of it.
    """
    sites = patch_sites(mask)
    if not sites:
        return float("nan")
    half = window // 2
    spreads: list[float] = []
    for row, column in sites:
        patch = grey[row - half:row + half + 1,
                     column - half:column + half + 1]
        inside = mask[row - half:row + half + 1,
                      column - half:column + half + 1]
        if inside.sum() < patch.size * 0.75:
            continue
        values = patch[inside]
        spreads.append(float(values.max()) - float(values.min()))
    if not spreads:
        return float("nan")
    return float(np.median(spreads))


def warm_fraction(image: "np.ndarray", mask: "np.ndarray",
                  margin: int = 4) -> float:
    """Share of the masked pixels whose red channel leads their green.

    **Red against green, and the first version of this used red against blue.**
    That version reported the finish getting *cooler* - 0.6% to 0.2% - on a
    frame whose midground had turned by 44 levels of red-minus-blue and plainly
    looked warmer beside its control. Both numbers were correct and the measure
    was wrong, for a reason worth writing down:

      * this world is lit by a cool key, a cyan rim and a blue bounce, so the
        blue channel leads *everything*. A rock can warm by forty levels and
        still be forty short of crossing over, and a threshold on `R - B` is
        therefore a threshold on the lighting rather than on the surface.
      * green is the channel that separates warm from teal. `WorldWarm` is
        #FFAE62 and `WorldRim` is #63BEE8: both carry a lot of green, so a
        surface that is merely *lighter* raises green with red, and only one
        that is actually turning raises red past it.

    So `R > G` is the crossing that corresponds to what a viewer calls warm
    here, and it moved 0.1% to 25.6% on the same pair of frames that `R - B`
    called a regression.

    The world is cool by construction and stays cool by instruction, so this is
    never expected to be large. `margin` keeps a neutral grey out of the count.
    """
    total = int(mask.sum())
    if total == 0:
        return float("nan")
    red = image[..., 0].astype(np.int16)
    green = image[..., 1].astype(np.int16)
    return float(((red - green) > margin)[mask].sum()) / float(total)


def warm_shift(image: "np.ndarray", mask: "np.ndarray") -> float:
    """Median `R - B` over a band, in levels. Signed, and usually negative.

    Reported beside `warm_fraction` rather than instead of it: the fraction
    says how much of a band has crossed over, and this says how far the rest
    of it moved. A pass that turned the whole world warm by five levels and
    crossed nothing would show up here and nowhere else.
    """
    if int(mask.sum()) == 0:
        return float("nan")
    return float(np.median(
        (image[..., 0].astype(np.int16) - image[..., 2].astype(np.int16))[mask]))

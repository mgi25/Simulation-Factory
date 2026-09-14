"""V25: the world-density variants, the frames they are judged on, and how.

This is the Python half of the world lab. The Godot half is
`godot/assets/marble_machine/environment/environment_world.gd`, which builds
near-world geometry from a profile's `world` section; this module says **which
variants** there are, **which frames and spans** they are compared on, and
**what is measured** on them.

## The comparison is fair by construction, exactly as V23's was

Every variant is photographed through the same solved V22.1 camera tracks, at
the same output seconds, from the same locked replay, with the same start
contract, the same `--machine=v23b` and the same `--finish-sign=double`.
Nothing here re-solves a camera, re-seeds a scatter or re-runs a physics step.
Two frames that differ differ only in how much world is in them.

## What a number here can and cannot say

V23 established the rule this lab inherits: **depth is shown, not scored**. It
tried three ways of scoring layering from a rendered frame and all three turned
out to be measuring brightness under another name, and that verdict stands -
`v23_env.plateaus` carries the full account. So the measures here are of two
kinds, and neither claims to see "3D-ness":

* **Constraint measures**, which say whether the world has broken something.
  `headroom` (the machine's own brightness minus the backdrop's), marble
  `separation`, and `clip` are V21's and V23's, unchanged, and they are the
  reason a richer world cannot be declared better just for being richer.
* **Fact measures**, which say what is actually drawn and where.
  `layer_cover` is the share of frame each depth band occupies, read off a
  marker render rather than guessed; `layer_value` is each band's mean L* in
  the delivered frame, which is what "three readable recession layers" means
  operationally; and `parallax` is the measured per-layer image shift between
  two frames of a moving shot.

**`parallax` is the one new measurement, and it is a measurement rather than a
score.** For a camera move of known duration, each depth band's mask is taken
from the marker render and the band's own pixels are phase-correlated between
the two frames. The result is a displacement in pixels. A world with real depth
in it produces a monotone series - nearest fastest, furthest slowest - and a
backdrop produces a flat one. That is a fact about the frames, and it is the
only honest answer to "does the camera move make this look three-dimensional".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

# --- the variants -----------------------------------------------------------


@dataclass(frozen=True)
class Variant:
    """One world-density setting, as the lab refers to it.

    `key` is the string passed to Godot as `--environment=`; it must name a
    profile in `environment/profiles/index.json`, and
    `tests/test_sloped_v25_world.py` checks that the two lists agree.
    """

    key: str
    title: str
    blurb: str


BASELINE = Variant(
    "aurora_valley",
    "V23 baseline",
    "the accepted V23 world: Aurora Valley with no near-world geometry at all",
)

VARIANTS: tuple[Variant, ...] = (
    Variant(
        "aurora_valley_v25a",
        "A - Restrained",
        "landform only: valley walls, midground ridges, cut scarps, skyline "
        "spires and a ravine floor",
    ),
    Variant(
        "aurora_valley_v25b",
        "B - Balanced premium",
        "A plus foreground rock, support foundations, sparse conifers, one "
        "landmark per race location and three distant practicals",
    ),
    Variant(
        "aurora_valley_v25c",
        "C - Rich showcase",
        "B with every count raised, a denser gorge mist and a thicker valley "
        "haze",
    ),
)

#: The diagnostic profiles that paint each depth band a flat identifying hue -
#: one per variant plus one over the V23 baseline. Not a look: they exist so
#: `layer_cover`, `layer_value` and `parallax` are read off a segmentation of
#: the *same* geometry rather than off a guess about what is where, and there
#: is one per variant because A, B and C do not have the same geometry.
MARKERS: dict[str, str] = {
    BASELINE.key: "_marker_v25_base",
    "aurora_valley_v25a": "_marker_v25a",
    "aurora_valley_v25b": "_marker_v25b",
    "aurora_valley_v25c": "_marker_v25c",
}


def marker(key: str) -> str:
    if key not in MARKERS:
        raise KeyError(f"no V25 marker for {key!r}")
    return MARKERS[key]

ALL: tuple[Variant, ...] = (BASELINE,) + VARIANTS


def variant(key: str) -> Variant:
    for entry in ALL:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25 variant named {key!r}")


# --- the frames -------------------------------------------------------------


@dataclass(frozen=True)
class Moment:
    """One comparison frame: which track, which output second, and why."""

    key: str
    track: str
    second: float
    title: str
    why: str


# The ten the brief names, in race order, plus three preview frames - the only
# framings on this course that see the whole valley at once, and therefore the
# only place the far bands can be judged on composition rather than on cover.
#
# The race seconds are inside the cut they name on the V22.1 track:
#
#     start 0.00-4.55   descent 4.55-7.52   obstacle 7.52-12.95
#     fork 12.95-14.58  branches 14.58-16.27  merge 16.27-16.75
#     final 16.75-22.32
MOMENTS: tuple[Moment, ...] = (
    Moment("start", "race", 0.600, "1  Start",
           "eight marbles on the line, and the one frame with the start "
           "backboard filling a third of it"),
    Moment("mixer", "race", 3.000, "2  Mixer",
           "the rotor, still on the start cut, with the shelf above the "
           "course in shot"),
    Moment("descent", "race", 5.800, "3  Descent",
           "the first shot with terrain above and the gorge below at once"),
    Moment("obstacle", "race", 10.200, "4  Obstacle",
           "the longest cut; the uphill wall is the whole left of the frame"),
    Moment("fork_approach", "race", 12.400, "5  Fork approach",
           "the last of the obstacle cut, where the fork gate first appears"),
    Moment("split", "race", 13.600, "6  Split",
           "the choice; the gate landmark either side of the route"),
    Moment("branch", "race", 15.400, "7  Branch",
           "two routes over open air: the depth shot of the whole film"),
    Moment("merge", "race", 16.500, "8  Merge",
           "the routes rejoining, with the finish mesa already in frame"),
    Moment("final_approach", "race", 18.600, "9  Final approach",
           "the viaduct over the valley, the highest the track ever stands"),
    Moment("finish", "race", 21.400, "10  Finish",
           "the gold payoff, parked up-course of a double-sided board"),
    Moment("preview_arena", "preview", 0.300, "P1  Preview - finish arena",
           "the widest view of the mesa, and the frame the film opens on"),
    Moment("preview_mid", "preview", 1.500, "P2  Preview - mid course",
           "the reverse dolly at its furthest out: whole-course scale"),
    Moment("preview_start", "preview", 2.900, "P3  Preview - the start",
           "the handoff frame, where the world has to sell the drop below"),
)

PREVIEW_MOMENTS = tuple(one for one in MOMENTS if one.track == "preview")
RACE_MOMENTS = tuple(one for one in MOMENTS if one.track == "race")

#: The three the brief calls "wide depth shots". They are the preview's, and
#: they are separated out because they are the only frames where a judgement
#: about the far bands is worth making.
WIDE = ("preview_arena", "preview_mid", "preview_start")


def moment(key: str) -> Moment:
    for entry in MOMENTS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25 moment named {key!r}")


def seconds_for(track: str) -> tuple[float, ...]:
    return tuple(one.second for one in MOMENTS if one.track == track)


# --- the close crops --------------------------------------------------------


@dataclass(frozen=True)
class Crop:
    """A rectangle of one moment, at full resolution, for a detail read.

    `box` is `(left, top, right, bottom)` as fractions of the frame, so the
    same crop lands in the same place whatever the render resolution is.
    """

    key: str
    moment: str
    box: tuple[float, float, float, float]
    title: str


# Six, each aimed at one thing the brief asks a question about, and each chosen
# because a full frame at 1080x1920 shrunk to a sheet cell cannot answer it.
CROPS: tuple[Crop, ...] = (
    Crop("embedding", "final_approach", (0.06, 0.30, 0.92, 0.84),
         "where the piers meet the ground on the viaduct"),
    Crop("anchor", "obstacle", (0.30, 0.44, 1.00, 0.92),
         "a support foundation on the terrace"),
    Crop("scarp", "obstacle", (0.00, 0.10, 0.55, 0.55),
         "the cut ledges on the uphill wall"),
    Crop("gate", "split", (0.10, 0.02, 1.00, 0.48),
         "the fork gate, either side of the choice"),
    Crop("gorge", "branch", (0.28, 0.30, 1.00, 0.86),
         "the drop beside the branches"),
    Crop("vegetation", "final_approach", (0.00, 0.22, 0.60, 0.68),
         "conifers against rock, at the scale they are read at"),
    Crop("payoff", "finish", (0.05, 0.05, 0.95, 0.55),
         "the finish board, and what is behind it"),
)


# --- the moving proofs ------------------------------------------------------


@dataclass(frozen=True)
class Clip:
    """A continuous span, rendered per variant as a moving proof."""

    key: str
    track: str
    start: float
    end: float
    title: str
    why: str


CLIPS: tuple[Clip, ...] = (
    Clip("full", "race", 0.000, 22.317,
         "the whole race, end to end",
         "the substantial motion proof the brief asks for: every cut, every "
         "camera move, at delivery length"),
    Clip("choice", "race", 12.950, 16.750,
         "fork to merge",
         "the shot that crosses the gorge, and the one with the most lateral "
         "camera travel per second in the film - where parallax either reads "
         "or does not"),
    Clip("preview", "preview", 0.000, 3.483,
         "the course preview, whole",
         "the only flight that sees the whole valley, and the frame the film "
         "opens on"),
)


def clip(key: str) -> Clip:
    for entry in CLIPS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25 clip named {key!r}")


# --- the depth bands --------------------------------------------------------


@dataclass(frozen=True)
class Layer:
    """One depth band, its marker hue, and roughly where it stands.

    `hue` is the flat RGB the `_marker_v25` profile paints the band, and the
    segmentation is nearest-hue among these with a chroma floor - see
    `segment`. `order` is the depth ordering the parallax test checks against,
    smallest nearest.
    """

    key: str
    title: str
    hue: tuple[int, int, int]
    order: int
    about: str
    #: Whether this band takes part in the depth ordering the parallax test
    #: checks. Two do not, and for the same reason: they are not at *a* depth.
    #: The near ground is one heightfield spanning five to ninety-five units
    #: from the lens, and the ravine floor is seventy units below the racing
    #: line at wildly varying range. Both are measured and reported; neither
    #: can be placed in a series that is about distance.
    ranked: bool = True


LAYERS: tuple[Layer, ...] = (
    Layer("terrain", "near ground", (255, 60, 120), 0,
          "the heightfield the course is cut into, 0-95 units", ranked=False),
    Layer("foreground", "foreground rock", (255, 0, 200), 1,
          "boulders, spires, scarps and support foundations, 4-40 units from "
          "the racing line"),
    Layer("vegetation", "vegetation", (255, 120, 0), 1,
          "conifers and shrubs, on the same ground as the foreground rock"),
    Layer("ridges", "midground ridges", (170, 255, 0), 2,
          "the far side of the gorge and the valley's inner wall, 100-240"),
    Layer("walls", "valley walls", (0, 230, 160), 3,
          "the outer wall, 300-390"),
    Layer("ranges", "distant ranges", (0, 220, 255), 4,
          "V23's own three mass rings, 206-740"),
    Layer("water", "ravine floor", (140, 0, 255), 1,
          "the water and its banks, at the bottom of the gorge", ranked=False),
)

#: Which palette keys each band is painted from in the marker profile.
#: `tools/sloped_v25_profiles.py` writes `_marker_v25.json` from this table, so
#: a new world surface that nobody adds here shows up as unmarked rather than
#: as somebody else's band - which is a visible hole in a sheet rather than a
#: silent misattribution in a number.
MARKED: dict[str, tuple[str, ...]] = {
    "terrain": ("slope_cliff", "slope_rock", "slope_earth", "slope_scree",
                "slope_cap", "slope_boulder", "slope_moss", "scrub_dark",
                "scrub_dry"),
    "foreground": ("world_rock", "world_scarp", "world_soil", "world_deck",
                   "world_deck_dark"),
    "vegetation": ("conifer_deep", "conifer_dark", "world_shrub"),
    "ridges": ("world_cliff_face", "world_cliff_ledge"),
    "walls": ("world_wall_face", "world_wall_ledge"),
    "ranges": ("rock_soft_near", "rock_soft_mid", "rock_soft_far",
               "rock_soft_haze", "far_structure"),
    "water": ("world_water", "world_wet"),
}


def layer(key: str) -> Layer:
    for entry in LAYERS:
        if entry.key == key:
            return entry
    raise KeyError(f"no V25 layer named {key!r}")


#: Below this chroma a marker pixel is not a marked surface: it is sky, or the
#: machine, or an emissive piece of dressing that belongs to no depth band.
CHROMA_FLOOR = 22.0

#: How far, in CIELAB hue degrees, a rendered marker surface may sit from its
#: authored hue and still be that band.
#:
#: The marker surfaces are **unshaded and fog-disabled** - see
#: `lab_palette._retune` - so no light touches them, but the grade still does:
#: an ACES tone map at exposure 0.81 with saturation 1.30 moves a flat colour's
#: hue by up to about twelve degrees, consistently per hue. Measured on the
#: frames rather than assumed - the near ground's authored 10 degrees renders
#: at 5, the ridges' 122 at 110, the foreground's 339 at 333. The seven
#: authored hues are at least thirty degrees apart, so a half-gap tolerance
#: separates them with room to spare.
#:
#: **Two earlier versions of this were wrong in opposite directions, and both
#: were caught by a number that could not be true.** The first classified a
#: *lit* marker by hue and reported the V23 baseline - which has no foreground
#: rock whatsoever - as 22% foreground rock; that was the near ground drifting
#: a whole band over under the warm fill, and it is why the marker surfaces are
#: unshaded now. The second matched flat sRGB exactly and reported variant A -
#: which has thirteen valley walls and twenty-six ridges in it - as 0.0%,
#: because it had forgotten that the grade still runs on an unshaded surface.
HUE_TOLERANCE = 15.0


def _classify(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Nearest marker hue per pixel, and whether it is close enough to count.

    Hue angle in the CIELAB a*b* plane, which the grade largely preserves and
    which exposure and brightness do not touch at all. See `HUE_TOLERANCE` for
    why this is an angle rather than an sRGB distance.
    """
    from sloped.v23_env import to_lab

    lab = to_lab(pixels)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    angle = np.arctan2(lab[..., 2], lab[..., 1])
    references = []
    for entry in LAYERS:
        hue = to_lab(np.array(entry.hue, dtype=np.float64))
        references.append(np.arctan2(hue[2], hue[1]))
    reference = np.array(references)
    delta = np.abs(np.angle(np.exp(1j * (angle[..., None] - reference))))
    nearest = np.argmin(delta, axis=-1)
    closest = np.take_along_axis(delta, nearest[..., None], axis=-1)[..., 0]
    marked = (chroma >= CHROMA_FLOOR) & (closest <= math.radians(HUE_TOLERANCE))
    return nearest, marked


def segment(pixels: np.ndarray,
            world_only: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Per-layer boolean masks of the **visible** world, from marker frames.

    ## The machine has to be subtracted, and the first version did not

    A marker render paints the world and leaves the machine alone, and the
    machine is full of saturated colour: cyan edge lighting, a violet mixer, an
    orange fork, gold at the finish and eight saturated marbles. Nothing stops
    one of those landing within tolerance of a marker hue.

    So a pixel counts as a visible band only if it is marked *and* classified
    the same way in two renders of the same frame: the ordinary one, and one
    taken with `--layers=world`, which draws the world alone. Where the machine
    stands in front of the world the two disagree - the world-only frame says
    "ridge", the ordinary one says "pearl" - and the pixel is dropped. Where
    nothing is in front they agree, and the pixel is the world.

    `world_only` may be omitted, and then this is the naive segmentation. It is
    left possible because the parallax test segments the world-only frame on
    its own, where there is nothing to subtract.
    """
    nearest, marked = _classify(pixels)
    if world_only is not None:
        other, other_marked = _classify(world_only)
        marked = marked & other_marked & (nearest == other)
    out: dict[str, np.ndarray] = {}
    for index, entry in enumerate(LAYERS):
        out[entry.key] = marked & (nearest == index)
    return out


def layer_cover(masks: dict[str, np.ndarray]) -> dict[str, float]:
    """Each band's share of the frame, as a percentage."""
    return {key: float(mask.mean() * 100.0) for key, mask in masks.items()}


def layer_value(pixels: np.ndarray, masks: dict[str, np.ndarray],
                floor: int = 400) -> dict[str, float]:
    """Each band's mean L* **in a delivered frame**, masked by the marker.

    The mask comes from the marker render and the values from the real one, so
    this is the lightness of the rock that is actually shipped rather than of
    the diagnostic paint. `floor` is the smallest mask worth reporting: below a
    few hundred pixels a band's mean is an edge artefact.
    """
    from sloped.v23_env import to_lab

    lightness = to_lab(pixels)[..., 0]
    out: dict[str, float] = {}
    for key, mask in masks.items():
        if int(mask.sum()) < floor:
            continue
        out[key] = float(lightness[mask].mean())
    return out


def recession(values: dict[str, float]) -> list[tuple[str, str, float]]:
    """Adjacent depth bands and the L* step between them, nearest first.

    The operational form of "at least three clearly readable recession
    layers": bands are grouped by `Layer.order`, each group's mean taken, and
    the step to the next group reported. A step is *readable* at about 4 L*,
    which is the just-noticeable difference for a large low-contrast field and
    the same threshold V23's range separation was argued at.
    """
    grouped: dict[int, list[float]] = {}
    for key, value in values.items():
        grouped.setdefault(layer(key).order, []).append(value)
    ordered = sorted(grouped)
    out: list[tuple[str, str, float]] = []
    for near, far in zip(ordered, ordered[1:]):
        a = float(np.mean(grouped[near]))
        b = float(np.mean(grouped[far]))
        out.append((_band_name(near), _band_name(far), b - a))
    return out


def _band_name(order: int) -> str:
    names = [one.title for one in LAYERS if one.order == order]
    return " + ".join(sorted(set(names)))


# --- parallax ---------------------------------------------------------------


#: Half-width of a tracked patch, in pixels. 20 gives a 41x41 template, which
#: at 1080x1920 is large enough to contain a rock's own shading gradient and
#: small enough that eight of them fit inside a band that covers 3% of a frame.
PATCH = 20

#: How far a patch is searched for in the second frame, and at what step. The
#: coarse pass steps 4 px over +/-72, the fine pass steps 1 px over +/-4 of the
#: coarse winner. 72 px is the most any band moves in a quarter second on this
#: camera language, checked against the widest move in the film.
SEARCH = 72
COARSE = 4

#: A patch flatter than this in L* has nothing for a matcher to lock onto, and
#: a match on it is noise wearing a number. Most of the world is dark rock, so
#: this is deliberately low - but it is not zero, and the count of patches that
#: survived it is reported beside every displacement.
TEXTURE_FLOOR = 1.4

#: How many patches to track per band, at most. The reported displacement is
#: their median, so an odd number and enough of them to outvote one bad match.
PATCHES = 9


def _grey(pixels: np.ndarray) -> np.ndarray:
    from sloped.v23_env import to_lab

    return to_lab(pixels)[..., 0]


def _patch_sites(mask: np.ndarray, limit: int = PATCHES) -> list[tuple[int, int]]:
    """Centres for up to `limit` templates lying wholly inside `mask`.

    A template that straddles the band's edge contains a piece of whatever is
    behind it, and whatever is behind it is at a different depth and moving at
    a different rate - so the match would be of a blend of two bands. The test
    is exact rather than approximate: the integral image gives the mask's sum
    over each candidate window in one lookup, and a window is only used when
    that sum is the whole window.
    """
    height, width = mask.shape
    edge = PATCH + SEARCH + 1
    if height <= 2 * edge or width <= 2 * edge:
        return []
    area = np.cumsum(np.cumsum(mask.astype(np.int32), axis=0), axis=1)

    def inside(y: int, x: int) -> bool:
        y0, x0 = y - PATCH - 1, x - PATCH - 1
        y1, x1 = y + PATCH, x + PATCH
        total = area[y1, x1]
        if y0 >= 0:
            total -= area[y0, x1]
        if x0 >= 0:
            total -= area[y1, x0]
        if y0 >= 0 and x0 >= 0:
            total += area[y0, x0]
        return int(total) == (2 * PATCH + 1) ** 2

    # A coarse grid rather than the brightest or largest blob: patches spread
    # over the band sample its whole extent, and a band that is only tracked
    # where it happens to be densest is tracked where it is least likely to be
    # moving like the rest of it.
    step = max(48, min(height, width) // 24)
    sites: list[tuple[int, int]] = []
    for y in range(edge, height - edge, step):
        for x in range(edge, width - edge, step):
            if inside(y, x):
                sites.append((y, x))
    if len(sites) <= limit:
        return sites
    stride = len(sites) / float(limit)
    return [sites[int(index * stride)] for index in range(limit)]


def _match(template: np.ndarray, frame: np.ndarray, y: int, x: int,
           reach: int, step: int) -> tuple[int, int, float]:
    """Best zero-mean normalised cross-correlation offset, searched on a grid.

    Brute force over offsets rather than an FFT, because the search window is
    small and the arithmetic is then obviously the arithmetic that is meant:
    an FFT correlation needs its normalisation built from integral images and
    that is where a silent sign or off-by-one lives.
    """
    base = template - template.mean()
    norm = float(np.sqrt((base * base).sum()))
    if norm < 1e-6:
        return (0, 0, 0.0)
    best = (0, 0, -2.0)
    for dy in range(-reach, reach + 1, step):
        for dx in range(-reach, reach + 1, step):
            window = frame[y + dy - PATCH:y + dy + PATCH + 1,
                           x + dx - PATCH:x + dx + PATCH + 1]
            if window.shape != template.shape:
                continue
            centred = window - window.mean()
            scale = float(np.sqrt((centred * centred).sum()))
            if scale < 1e-6:
                continue
            score = float((base * centred).sum()) / (norm * scale)
            if score > best[2]:
                best = (dy, dx, score)
    return best


def band_shift(before: np.ndarray, after: np.ndarray, mask: np.ndarray
               ) -> dict[str, float]:
    """How far one depth band's content moved between two delivered frames.

    Block matching: up to nine 41x41 templates taken from inside the band in
    the first frame, each searched for in the second over a window far larger
    than itself, and the median of the winning offsets reported.

    ## Two earlier versions of this measured nonsense, in opposite directions

    **The first correlated the delivered frames, both windowed by one mask**
    taken from the first of them, and reported 0.0 px for every band in every
    shot. Applying the same window to both images puts one identical, enormous,
    high-contrast shape - the window's own edge - into both; the correlation
    locks onto that, it has not moved, and everything measures zero.

    **The second correlated the two frames' own band masks against each other**,
    on the reasoning that a silhouette is what translates. It reported 386 px
    for a distant range and 0 px for the near ground. A band's mask changes
    shape because the machine occludes a different part of it, not only because
    it moved, and a mask that changes shape has no translation to find - while
    the near ground's mask fills the frame in both and cannot appear to move at
    all.

    What is left is the textbook answer and it is textbook for a reason: track
    *content*, from a window that lies wholly inside the band, searched over a
    region larger than the window. The returned `patches` count is part of the
    measurement - a displacement from two patches is a different claim from one
    from nine.
    """
    sites = _patch_sites(mask)
    if not sites:
        return {"patches": 0}
    first = _grey(before)
    second = _grey(after)
    offsets: list[tuple[float, float, float]] = []
    for y, x in sites:
        template = first[y - PATCH:y + PATCH + 1, x - PATCH:x + PATCH + 1]
        if float(template.std()) < TEXTURE_FLOOR:
            continue
        dy, dx, score = _match(template, second, y, x, SEARCH, COARSE)
        if score <= 0.0:
            continue
        fy, fx, score = _match(template, second, y + dy, x + dx,
                               COARSE - 1, 1)
        offsets.append((dx + fx, dy + fy, score))
    if not offsets:
        return {"patches": 0}
    dxs = sorted(one[0] for one in offsets)
    dys = sorted(one[1] for one in offsets)
    middle = len(offsets) // 2
    dx = float(dxs[middle])
    dy = float(dys[middle])
    return {
        "patches": len(offsets),
        "dx": dx,
        "dy": dy,
        "shift": float(math.hypot(dx, dy)),
        "score": float(np.median([one[2] for one in offsets])),
        # The spread across patches, as the honest error bar: a band that is
        # rotating or receding does not have one displacement, and a wide
        # spread says so rather than hiding behind a median.
        "spread": float(np.hypot(np.std(dxs), np.std(dys))),
    }


def parallax(before: np.ndarray, after: np.ndarray,
             masks: dict[str, np.ndarray],
             min_cover: float = 0.4) -> dict[str, dict[str, float]]:
    """Per-band displacement between two delivered frames of a moving shot.

    `masks` is the band segmentation of the first frame. `min_cover` drops a
    band too small for nine patches to sample meaningfully; it is reported
    rather than silently skipped, so the caller gets `cover` for every band and
    a displacement only for the ones that earned it.
    """
    out: dict[str, dict[str, float]] = {}
    for entry in LAYERS:
        mask = masks[entry.key]
        cover = float(mask.mean() * 100.0)
        row: dict[str, float] = {"cover": cover, "order": float(entry.order)}
        if cover >= min_cover:
            row.update(band_shift(before, after, mask))
        out[entry.key] = row
    return out


def monotone(rows: dict[str, dict[str, float]]) -> tuple[bool, str]:
    """Whether measured displacement falls with depth, and what it did.

    The parallax claim in one line. Bands are grouped by depth order, each
    group's mean shift taken over the bands that were actually tracked, and the
    series checked for being non-increasing. The half-pixel slack is because a
    block match is quantised to whole pixels and two bands at genuinely the
    same rate can land one apart.

    **The near ground and the ravine floor are excluded, and that is not
    convenient rounding.** Neither is at a depth. The near ground is a single
    heightfield running from five units in front of the lens to ninety-five
    behind the course, so its tracked patches sample the whole range at once
    and its median is an average over every distance in the shot; the ravine
    floor is seventy units below the racing line at a range that changes by a
    factor of three between two cuts. Both are measured, both are printed, and
    neither can be placed in a series that is about distance. The first version
    of this ranked the near ground first and reported five moves out of five as
    not monotone - with the *world* bands falling cleanly in every one of them.
    """
    grouped: dict[int, list[float]] = {}
    for key, row in rows.items():
        if "shift" not in row or int(row.get("patches", 0)) < 2:
            continue
        if not layer(key).ranked:
            continue
        grouped.setdefault(int(row["order"]), []).append(row["shift"])
    if len(grouped) < 2:
        return (False, "fewer than two bands were tracked")
    ordered = sorted(grouped)
    series = [float(np.mean(grouped[one])) for one in ordered]
    # **The ratio is the number worth reading, not the boolean.** Image motion
    # is rotation plus translation-over-depth, and rotation moves every band by
    # the same amount. A cut that mostly pans therefore reports every band
    # within a few per cent of every other and is *correctly* flat - there is
    # no parallax in a pan, whatever is in the world. A cut that travels
    # reports a ratio, and the ratio is how much depth the move revealed.
    strength = series[0] / max(series[-1], 0.5)
    text = " > ".join(f"{one:.1f}" for one in series) + f"  ({strength:.1f}x)"
    for near, far in zip(series, series[1:]):
        if far > near + 0.5:
            return (False, f"not monotone: {text}")
    return (True, text)


def separation(rows: dict[str, dict[str, float]]) -> dict[str, float]:
    """How many world bands moved, and how differently. The parallax verdict.

    ## Why this replaced "is the series monotone", and what a chase camera does

    The brief asks to verify that foreground moves fastest, midground slower
    and background slowest. That ordering is the ordering of a camera flying
    through a static scene, and **it is not the ordering of a camera that is
    tracking something**, which is what every race camera on this course is.

    A tracking camera pins its subject: the pack is held at the same place in
    frame for the length of the cut, so a static point at the *pack's own
    distance* barely moves at all, and image velocity grows in both directions
    from there - nearer things sweep one way, further things the other. The
    measured tables say exactly that. At `obstacle_pan` the foreground moves 19
    px while the ridges move 61: the foreground rock there is beside the pack,
    at the distance the camera is holding, and the ridges are two hundred units
    past it.

    So "monotone" is the wrong question for this camera language, and it is
    kept only as a note. The right question is whether the bands move at
    *different* rates at all, because that - and not their order - is what an
    eye reads as three-dimensional. A painted backdrop gives one rate. A world
    gives a spread.

    Returns the count of tracked world bands, the slowest and fastest of them,
    and the ratio between. `bands` of 0 or 1 means the question cannot be asked
    of that frame: there is not enough world in it to have a spread.
    """
    speeds: list[float] = []
    for key, row in rows.items():
        if "shift" not in row or int(row.get("patches", 0)) < 2:
            continue
        if not layer(key).ranked:
            continue
        speeds.append(float(row["shift"]))
    if not speeds:
        return {"bands": 0.0, "slowest": 0.0, "fastest": 0.0, "spread": 0.0}
    slow = min(speeds)
    fast = max(speeds)
    return {
        "bands": float(len(speeds)),
        "slowest": slow,
        "fastest": fast,
        "spread": fast / max(slow, 0.5),
    }


def verdict(rows: dict[str, dict[str, float]]) -> str:
    """One line per camera move, for the report."""
    got = separation(rows)
    bands = int(got["bands"])
    if bands < 2:
        return f"{bands} world band tracked - no spread to measure"
    return (f"{bands} bands, {got['slowest']:.0f}-{got['fastest']:.0f} px, "
            f"{got['spread']:.1f}x spread")


# --- phone readability ------------------------------------------------------

#: The size the brief says the film is actually judged at.
PHONE = (270, 480)


def phone(pixels: np.ndarray) -> np.ndarray:
    """One frame at phone size, resampled the way a phone would.

    Pillow's LANCZOS, because that is what the sheet tools use and because a
    nearest-neighbour downscale would flatter thin bright geometry - a lamp
    mast that survives at 270 px only because a nearest sample happened to
    land on it has not survived.
    """
    from PIL import Image

    return np.asarray(
        Image.fromarray(pixels).resize(PHONE, Image.LANCZOS).convert("RGB")
    )


def noise(pixels: np.ndarray, band: tuple[float, float] = (0.30, 1.0)) -> float:
    """Local contrast energy in the lower part of a phone-size frame.

    The brief's "the world must not become visual noise", as something that
    can be compared between variants: the mean absolute Laplacian over the
    band of the frame the course occupies. It is a *relative* number - a value
    means nothing on its own, and C being well above A means C's world has
    more small high-contrast detail in it, which at phone size is the
    definition of noise.
    """
    from sloped.v23_env import to_lab

    lightness = to_lab(pixels)[..., 0]
    top = int(round(lightness.shape[0] * band[0]))
    bottom = int(round(lightness.shape[0] * band[1]))
    view = lightness[top:bottom]
    if view.shape[0] < 3 or view.shape[1] < 3:
        return 0.0
    laplace = (
        4.0 * view[1:-1, 1:-1]
        - view[:-2, 1:-1] - view[2:, 1:-1]
        - view[1:-1, :-2] - view[1:-1, 2:]
    )
    return float(np.abs(laplace).mean())


# --- the cost ---------------------------------------------------------------


@dataclass(frozen=True)
class Cost:
    """What one variant costs to draw, as the renderer reports it."""

    meshes: int
    triangles: int
    milliseconds: float

    def line(self) -> str:
        return (f"{self.meshes} meshes, {self.triangles / 1000.0:.0f}k "
                f"triangles, {self.milliseconds:.0f} ms/frame")


def parse_cost(stdout: str) -> Cost:
    """Pull the mesh, triangle and frame-time counts out of a render's log.

    `sloped_race_render` prints both lines on every run; parsing them is how
    the performance table is built from the same render that made the frames,
    rather than from a second run that might have been of something else.
    """
    meshes = 0
    triangles = 0
    milliseconds = 0.0
    for line in stdout.splitlines():
        if line.startswith("scene: ") and "mesh instances" in line:
            parts = line.replace("scene: ", "").split()
            meshes = int(parts[0])
            triangles = int(parts[3].lstrip("~"))
        elif line.startswith("rendered ") and "ms/frame" in line:
            milliseconds = float(line.split("(")[1].split()[0])
    return Cost(meshes, triangles, milliseconds)


def census_of(stdout: str) -> dict[str, int]:
    """The near world's own census, as `course_scene` printed it."""
    for line in stdout.splitlines():
        if not line.strip().startswith("world: "):
            continue
        out: dict[str, int] = {}
        for part in line.strip()[len("world: "):].split(","):
            bits = part.split()
            if len(bits) == 2:
                out[bits[0]] = int(bits[1])
        return out
    return {}


def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return float(0.5 * (ordered[middle - 1] + ordered[middle]))


def table(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    """A plain fixed-width table, for a report that is read in a terminal."""
    widths = [max(len(str(column)),
                  max((len(str(row.get(column, ""))) for row in rows),
                      default=0))
              for column in columns]
    out = ["  ".join(str(c).ljust(w) for c, w in zip(columns, widths)),
           "  ".join("-" * w for w in widths)]
    for row in rows:
        out.append("  ".join(str(row.get(c, "")).ljust(w)
                             for c, w in zip(columns, widths)))
    return "\n".join(out)

"""Write the four V25 environment profiles from one place.

    python tools/sloped_v25_profiles.py

**Why a generator and not four hand-written JSON files.** The three density
variants are the same world at three settings, and the whole comparison is only
fair if the settings are the *only* difference between them. Four files edited
by hand drift: a bearing gets nudged in B and not in A, and the sheet then
compares two worlds rather than two densities. Here A is a table, B is A plus a
named set of additions, C is B with counts scaled, and the file each one writes
is a delta over `aurora_valley_v25` - which is itself a delta over the shipped
`aurora_valley`. Nothing is duplicated and nothing can drift.

The generated files are committed; this script is how they are regenerated, and
`tests/test_sloped_v25_world.py` checks that re-running it is a no-op.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT_FOR_IMPORT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT_FOR_IMPORT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_FOR_IMPORT)

from sloped import v25_world

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(PROJECT_ROOT, "godot", "assets", "marble_machine",
                           "environment", "profiles")

# --- where the cameras go ---------------------------------------------------
#
# **Both solved V22.1 tracks, decimated to four-unit spacing in plan.** A world
# form has to stay clear of two things: the racing line, which is obvious, and
# the *camera path*, which is not and which cost a whole render pass to find.
# The start camera stands on the hillside four units above the ground and
# twenty-two from its subject; a scarp authored on that same hillside came out
# seven units from the lens and filled the entire mixer frame with a black
# wall, in all three variants at once.
#
# It is a constant here rather than something the scene reads from a loaded
# track, because the race and the preview are two tracks photographing one
# build: a world that avoided whichever track happened to be loaded would be a
# different world in the two renders. Regenerate with
# `tools/sloped_v25_profiles.py --camera-path` when a camera solve changes -
# and a camera solve changing is a V22.1 decision, not a V25 one, so this list
# is expected to be stable.

CAMERA_PATH = [
    [-33.7, -52.9], [-35.7, -49.4], [-36.9, -45.5], [-37.3, -41.5],
    [-28.6, -53.9], [-29.1, -49.7], [-29.8, -45.8], [-31.2, -42.0],
    [-32.6, -38.2], [-31.7, -34.3], [-28.1, -32.4], [-23.8, -33.1],
    [-19.7, -34.5], [-15.6, -36.0], [-11.4, -37.2], [-7.0, -37.8],
    [-2.9, -37.6], [-0.4, -34.4], [0.1, -30.4], [-3.5, -28.2],
    [-7.1, -25.8], [-10.0, -22.5], [-12.0, -18.8], [-14.4, -15.5],
    [-18.2, -14.2], [-21.7, -11.9], [-24.7, -9.2], [-26.9, -5.6],
    [-28.3, -1.6], [-23.4, -3.7], [-20.6, -6.7], [-18.0, -9.8],
    [-9.0, -16.0], [-5.1, -17.6], [-1.2, -19.3], [2.5, -20.9],
    [6.8, -21.5], [10.9, -20.4], [14.5, -18.4], [18.1, -15.2],
    [21.1, -11.6], [23.5, -8.2], [25.5, -4.3], [26.8, -0.0],
    [27.3, 4.0], [26.9, 8.2], [25.7, 12.2], [23.8, 15.8],
    [21.2, 19.2], [18.3, 22.3], [15.1, 25.0], [11.6, 27.5],
    [8.2, 29.7], [4.6, 31.7], [1.0, 33.4], [-2.8, 35.1],
    [10.5, 23.5], [9.4, 19.5], [8.3, 15.6], [7.0, 11.7],
    [5.7, 7.7], [4.4, 3.6], [3.3, -0.4], [2.1, -4.3],
    [0.7, -8.1], [-1.0, -11.9], [-10.8, -28.6], [-13.6, -32.3],
    [-18.9, -38.6], [-21.9, -41.8], [-25.0, -44.9],
]


# --- the shared pass: air, recession and the near-world palette --------------
#
# No geometry at all. This is the half of V25 that would still be worth having
# if every variant were rejected: four rock values that step cleanly, a fog that
# separates a hundred units from three hundred, and one cool light that only
# reaches the world layer.

BASE = {
    "id": "aurora_valley_v25",
    "title": "Aurora Valley V25",
    "family": "valley",
    "summary": (
        "Aurora Valley's air and materials, retuned for a world with "
        "geometry in it: five rock recession steps, valley-floor haze and a "
        "cool rim that reaches the world layer only"
    ),
    "extends": "aurora_valley",
    # **Denser, and pooled lower.** V23's fog was authored against a world
    # whose only distant geometry stood at 206 units or further; V25 puts rock
    # at 95. At 0.0034 the difference between a ridge at 110 and a wall at 240
    # is 0.31 against 0.56 of fog, which is real but shallow, and the two read
    # as one grey bank. At 0.0044 it is 0.38 against 0.65 - and, more usefully,
    # the foreground at 25 units still only takes 0.10, so nothing close gets
    # washed. `height` drops to the gorge lip and `height_density` doubles, so
    # the haze that was spread evenly through the frame now sits in the hole
    # the course runs along the edge of.
    "fog": {
        "colour": "#15293F",
        "energy": 0.55,
        "sun_scatter": 0.04,
        "density": 0.0038,
        "sky_affect": 0.38,
        "aerial_perspective": 0.94,
        "height": -40.0,
        "height_density": 0.030,
    },
    "lights": {
        # **The world key comes down and the fill comes with it.** V23 lit a
        # hillside that had nothing behind it, so the brightest large area in
        # the frame being the near ground cost nothing. With four bands of
        # rock behind it that same hillside inverts the recession: the nearest
        # plane is the lightest, which is what a viewer reads as "backdrop
        # painted behind a model". Two thirds of a stop off the key and a
        # little off the fill puts the ground back under the machine without
        # touching the hue.
        "WorldKey": {"energy": 1.65},
        "WorldFill": {"energy": 0.66},
        # The cool rake across the cliff faces, and the reason it is a sixth
        # light rather than a change to `Rim`: `Rim` is on cull mask
        # 0xFFFFFFFF and reaches the machine, where it is doing the job V21
        # tuned it for. A light that gave the rock an edge by brightening the
        # pearl shell would be spending the machine's own headroom on scenery.
        "WorldRim": {
            "cull_mask": 2,
            "colour": "#63BEE8",
            "energy": 0.55,
            "specular": 0.05,
            "rotation": [-7.0, 96.0, 0.0],
            "shadow": {"enabled": False},
        },
    },
    # Shared by every variant, and empty of features: the keep-out belongs to
    # this course and this camera language rather than to a density setting.
    "world": {"keepout": CAMERA_PATH},
    "palette": {
        # The five recession steps, measured in CIELAB L* rather than chosen
        # by eye. Nearest is darkest and holds the most local contrast;
        # furthest is lightest, least saturated and nearly edgeless.
        #
        #   world_scarp        11.0   foreground rock, 0-40 units
        #   world_cliff_face   14.2   midground ridges, 95-160
        #   rock_soft_near     12.2   the valley walls, 200-300  (V23's value)
        #   rock_soft_mid      17.2   V23's near range
        #   rock_soft_far      21.8   V23's mid range
        #   rock_soft_haze     26.6   V23's far range
        #
        # The walls reuse V23's own two nearest range values rather than
        # introducing more keys, which is why there are six rows above and only
        # two new materials: a shared material is a shared draw call, and the
        # recession is a property of the fog and the radii as much as of the
        # albedo.
        # **The near ground, two L* down and a third less saturated.** This
        # is V23's own weakness 3 - "the near ground is a fairly saturated
        # blue in the wide shots... the most likely thing a reviewer will want
        # dialled back" - and it stops being cosmetic the moment the world
        # behind it has geometry in it. With nothing beyond the terrain edge
        # a saturated hill was simply the world's colour; with four bands of
        # rock behind it, it is the *nearest* band, and a nearest band that is
        # both the lightest and the most chromatic inverts the recession.
        # Hue is untouched - the direction is Aurora's and stays Aurora's -
        # and the compressed value band V23 argued for is preserved, because
        # every row moves by the same two L*.
        "slope_cliff": {"albedo": "#1B212B"},
        "slope_rock": {"albedo": "#202733"},
        "slope_earth": {"albedo": "#2B3444"},
        "slope_scree": {"albedo": "#262F3F"},
        "slope_cap": {"albedo": "#242B38"},
        "slope_boulder": {"albedo": "#1A202A"},
        "slope_moss": {"albedo": "#1D2A25"},
        "scrub_dark": {"albedo": "#1A2420"},
        "scrub_dry": {"albedo": "#202828"},
        "world_rock": {"albedo": "#0C1119"},
        "world_scarp": {"albedo": "#0F141D"},
        "world_cliff_face": {"albedo": "#111826"},
        "world_cliff_ledge": {"albedo": "#19222F"},
        "world_wall_face": {"albedo": "#151E2E"},
        "world_wall_ledge": {"albedo": "#1E2A3C"},
        "world_soil": {"albedo": "#1B2231"},
        "world_deck": {"albedo": "#2A3140"},
        "world_deck_dark": {"albedo": "#171C25"},
        # Wet rock and water in the gorge, both a step below the darkest dry
        # rock so the bottom of the ravine is the darkest thing in the world.
        "world_wet": {"albedo": "#101724", "roughness": 0.55},
        "world_water": {"albedo": "#091220", "roughness": 0.11,
                        "metallic": 0.4},
        # Vegetation: cool teal-greens, deliberately close to the rock in
        # value and separated from it by hue alone. A tree that reads as a
        # dark blob is doing its whole job; a tree that reads as *green* at
        # 270 pixels is a green thing near the marbles.
        "conifer_deep": {"albedo": "#0F241E"},
        "conifer_dark": {"albedo": "#16302A"},
        "world_shrub": {"albedo": "#1A2B26"},
        "lit_world_warm": {"albedo": "#3A2616", "emission": "#FFB469",
                           "energy": 2.0},
        "lit_world_cool": {"albedo": "#17303C", "emission": "#7FD8FF",
                           "energy": 1.6},
    },
}


# --- A: stronger terrain, minimal dressing ----------------------------------
#
# Landform only. Every form here is rock, and there is no vegetation, no
# engineering, no landmark and no added light. If B and C are both too much,
# this is what the world is.

WALLS = {
    "count": 13,
    "bearing_from": 296.0, "bearing_step": 25.0, "bearing_jitter": 7.0,
    "radius": 300.0, "radius_step": 46.0, "radius_cycle": 3,
    "height": 138.0, "height_step": -15.0, "height_cycle": 4,
    "base": 72.0, "base_step": 15.0, "base_cycle": 3,
    "taper": 0.30, "facets": 22, "tiers": 12, "sink": 18.0,
    "crest": 5, "crest_scale": 0.15, "crest_from": 0.6, "crest_span": 0.28,
    "seed_from": 601, "seed_step": 17,
    "materials": ["world_wall_face", "world_wall_ledge"],
}

# Two bands, and the reason there are two is the finding this pass turned on.
#
# The first ring was authored at radius 112-152, which is thirty units past the
# terrain's own edge and looked like the right place for a midground. It is
# not: these cameras stand 24 to 68 units from the terrain centre, so a mass at
# radius 130 can be **sixty units from the lens** and sixty units tall, and the
# marker render showed it filling half of four frames out of six and occluding
# the FINISH board in the payoff. A ring's radius has to be read against the
# *camera* envelope, not against the terrain's.
#
# So the midground proper went out to 188-240, where a 90-unit mass subtends
# about 25 degrees rather than 90; and the near band that is genuinely wanted -
# the far side of the gorge - became its own low, wide arc on the east side
# only, topping out forty units *below* the racing line so it can never reach
# the sky.
RIDGES = {
    "taper": 0.33, "facets": 26, "tiers": 13,
    "crest": 4, "crest_scale": 0.19, "crest_from": 0.58, "crest_span": 0.3,
    "seed_from": 811, "seed_step": 19,
    "materials": ["world_cliff_face", "world_cliff_ledge"],
    "bands": [
        {
            "count": 9,
            "bearing_from": 34.0, "bearing_step": 15.0, "bearing_jitter": 6.0,
            "radius": 100.0, "radius_step": 16.0, "radius_cycle": 2,
            "height": 42.0, "height_step": -7.0, "height_cycle": 3,
            "base": 21.0, "base_step": 4.0, "base_cycle": 2,
            "sink": 6.0, "seed_from": 907, "seed_step": 23,
        },
        {
            "count": 17,
            "bearing_from": 288.0, "bearing_step": 21.0, "bearing_jitter": 8.0,
            "radius": 188.0, "radius_step": 26.0, "radius_cycle": 3,
            "height": 90.0, "height_step": -11.0, "height_cycle": 4,
            "base": 33.0, "base_step": 7.0, "base_cycle": 3,
            "sink": 10.0,
        },
    ],
}

# Terrain-relative `[dx, dz, bearing, scale]`. Bearing is the direction the
# stack steps *back* into, which on this flank is uphill: 90 for the two
# lengthways walls, 0 up on the crest above the start.
SCARPS = {
    "tiers": 5, "size": [14.0, 1.5, 5.2], "rise": 1.75, "inset": 1.2,
    "shrink": 0.86, "sink": 1.5, "clearance": 7.0, "keepout": 14.0,
    "materials": ["world_scarp", "world_soil"],
    "sites": [
        [-58.0, -50.0, 90.0, 1.15],
        [-43.0, -24.0, 90.0, 1.00],
        [-40.0, 2.0, 90.0, 1.35],
        [-36.0, 28.0, 90.0, 1.10],
        [-48.0, -72.0, 60.0, 0.90],
        [-14.0, -78.0, 0.0, 1.20],
        [12.0, -72.0, 0.0, 1.00],
        [35.0, -28.0, 90.0, 1.10],
        [40.0, 6.0, 90.0, 1.30],
        [31.0, 34.0, 90.0, 1.00],
        [36.0, 60.0, 90.0, 1.15],
        [-12.0, 70.0, 20.0, 1.05],
    ],
}

SPIRES = {
    "count": 38, "zone": [-70.0, 48.0, -78.0, 30.0], "clearance": 10.0,
    "height": 7.0, "height_spread": 9.5, "base": 2.0, "taper": 0.66,
    "facets": 12, "tiers": 8, "sink": 1.2, "lean": 0.12, "min_normal": 0.58,
    "materials": ["world_rock", "world_scarp"],
}

RAVINE_A = {
    "water": True, "level": -70.0, "size": [84.0, 154.0], "round": 18.0,
    "at_x": 55.0, "at_z": 6.0, "material": "world_water", "banks": 0,
}

VARIANT_A = {
    "id": "aurora_valley_v25a",
    "title": "V25 A - Restrained",
    "summary": (
        "landform only: valley walls, midground ridges, cut scarps, skyline "
        "spires and a ravine floor. No vegetation, no engineering, no "
        "landmark, no added light."
    ),
    "extends": "aurora_valley_v25",
    "world": {
        "enabled": True,
        "walls": WALLS,
        "ridges": RIDGES,
        "scarps": SCARPS,
        "spires": SPIRES,
        "ravine": RAVINE_A,
    },
}


# --- B: balanced premium ----------------------------------------------------
#
# A, plus the four things that turn a landform into a place: rock in the
# foreground where the camera can sweep past it, foundations where the machine
# meets the ground, sparse vegetation for scale, and one memorable form at each
# race location. Plus three practicals and banks in the ravine.

BOULDERS = {
    "count": 72, "near": 7.0, "far": 32.0, "scale": 2.4, "scale_spread": 3.8,
    "taper": 0.44, "facets": 15, "tiers": 9, "sink": 0.5, "min_normal": 0.6,
    "materials": ["world_rock", "world_scarp"],
}

ANCHORS = {
    # **Eleven units, not twenty-two.** At the first spacing this placed five
    # anchors on two hundred and thirty-seven units of track, and none of the
    # five landed in any of the thirteen comparison frames - the brief's most
    # important request, measured at zero. The spacing is a *candidate*
    # interval and most candidates are rejected: an anchor is only built where
    # the track stands between `min_drop` and `max_drop` above the ground,
    # which is a narrow band on a course that is either benched into the hill
    # or flying over a gorge.
    "every": 15.0, "min_drop": 2.4, "max_drop": 17.0, "limit": 26,
    # **Four wide blocks, not seven narrow ones, and fifteen units apart
    # rather than eleven.** At the first setting that read there were 21
    # anchors of 7 blocks each - 147 rounded boxes along 237 units of track -
    # and in the choice clip they came out as a field of scattered cubes in
    # the lower half of the frame. The individual block is the right idea and
    # the count was wrong: at `block_width 0.52` four of them very nearly
    # close the arc, so an anchor reads as one wall with seams in it, which is
    # what masonry looks like. 56 boxes instead of 147.
    "pad": 4.6, "lip": 0.95, "blocks": 4, "wall": 1.7, "sweep": 1.12,
    "block_width": 0.52,
    "deck": "world_deck", "kerb": "world_deck_dark", "stone": "world_scarp",
}

TREES = {
    "clusters": 40, "per_cluster": 4, "cluster_spread": 3, "spread": 3.6,
    "height": 3.2, "height_spread": 2.8, "width": 0.6, "taper": 0.93,
    "facets": 8, "tiers": 5, "clearance": 7.0, "reach": 40.0,
    "min_normal": 0.72, "shrub_every": 3,
    "materials": ["conifer_deep", "conifer_dark"],
    "shrubs": ["world_shrub"],
}

# One form per race location, sited from the layout's own node table. The
# kinds are chosen for what each place has to communicate: a platform above the
# start, teeth at the obstacle, a *gate* at the fork because a route split
# should read as a junction, a narrowing at the merge and a rim at the finish.
LANDMARKS = {
    "clearance": 12.0, "keepout": 16.0,
    "sites": {
        "start": {"kind": "butte", "offset": [-30.0, 16.0], "height": 30.0,
                  "base": 15.0, "sink": 4.0, "taper": 0.24, "seed": 1301,
                  "material": "world_cliff_face"},
        "obstacle": {"kind": "spires", "offset": [-40.0, -20.0], "count": 3,
                     "height": 26.0, "base": 9.0, "spread": 6.0, "sink": 3.0,
                     "seed": 1409, "material": "world_scarp"},
        "split": {"kind": "gate", "offset": [3.0, 10.0], "bearing": 88.0,
                  "gap": 78.0, "height": 26.0, "base": 10.0, "ratio": 0.58,
                  "sink": 3.5, "seed": 1511, "material": "world_cliff_face"},
        "merge": {"kind": "spires", "offset": [-24.0, 10.0], "count": 3,
                  "height": 18.0, "base": 7.0, "spread": 5.0, "sink": 3.0,
                  "seed": 1607, "material": "world_scarp"},
        "finish": {"kind": "butte", "offset": [10.0, 34.0], "height": 30.0,
                   "base": 16.0, "sink": 3.0, "taper": 0.26, "seed": 1709,
                   "material": "world_cliff_face"},
    },
}

# `[node, dx, dy, dz, colour, energy, range, attenuation]`. Three, and the
# energies are a fifth of a zone practical's: these are meant to be read as
# distance, not as light.
LAMPS = {
    "sites": [
        ["obstacle", -22.0, -9.0, -6.0, "#FFB469", 0.9, 26.0, 1.6],
        ["split", 26.0, -16.0, 8.0, "#7FD8FF", 0.7, 30.0, 1.7],
        ["finish", 24.0, -5.0, 20.0, "#FFC98A", 1.1, 28.0, 1.5],
    ],
}

RAVINE_B = dict(RAVINE_A, banks=7, bank_material="world_wet",
                bank_offset=38.0, bank_span=120.0, bank_height=27.0,
                bank_base=15.0)

VARIANT_B = {
    "id": "aurora_valley_v25b",
    "title": "V25 B - Balanced premium",
    "summary": (
        "A, plus foreground rock, support foundations, sparse conifers, one "
        "landmark at each race location, three distant practicals and rock "
        "banks in the ravine"
    ),
    "extends": "aurora_valley_v25a",
    "world": {
        "boulders": BOULDERS,
        "anchors": ANCHORS,
        "trees": TREES,
        "landmarks": LANDMARKS,
        "lamps": LAMPS,
        "ravine": RAVINE_B,
    },
}


# --- C: rich showcase -------------------------------------------------------
#
# B with the counts raised and the atmosphere thickened. Present so that "B is
# enough" is a measured claim rather than an assumption - the brief asks for
# three densities and says B is the likely answer, and a lab that only built
# the likely answer has not tested it.

VARIANT_C = {
    "id": "aurora_valley_v25c",
    "title": "V25 C - Rich showcase",
    "summary": (
        "B with every count raised, a second ridge band, denser vegetation, "
        "more foreground rock and a thicker valley haze"
    ),
    "extends": "aurora_valley_v25b",
    "fog": {"density": 0.0044, "height_density": 0.042},
    "backdrop": {
        # The gorge mist V23 shipped, deepened. Its placement is V23's, which
        # took two attempts to get out of the sky - see `docs/
        # sloped_race_v23.md` §13 - and only `decks` and `alpha` move.
        "mist": {"decks": 8, "alpha": 0.085},
    },
    "world": {
        "walls": dict(WALLS, count=15, bearing_step=22.0),
        # C thickens the two authored bands rather than adding a third:
        # a band nobody has looked at through the marker is a band that
        # can occlude a payoff, which is how B's first ring was found.
        "ridges": dict(RIDGES, bands=[
            dict(RIDGES["bands"][0], count=13, bearing_step=10.0),
            dict(RIDGES["bands"][1], count=23, bearing_step=15.0),
        ]),
        "spires": dict(SPIRES, count=58),
        "boulders": dict(BOULDERS, count=118, far=36.0),
        "trees": dict(TREES, clusters=66, per_cluster=5, reach=48.0),
        "anchors": dict(ANCHORS, every=11.0, limit=34),
    },
}


# --- the marker -------------------------------------------------------------
#
# Not a look. `_marker_v25` is B with every world surface painted the flat hue
# its depth band is identified by, so `layer_cover`, `layer_value` and
# `parallax` are read off a segmentation of a real render rather than off a
# guess about what is where. It is written from `v25_world.MARKED` so the two
# cannot drift: a surface added to the world and not to that table shows up as
# a hole in the sheet rather than as somebody else's band.


def _marker(parent: str) -> dict:
    palette: dict = {}
    for band, keys in v25_world.MARKED.items():
        hue = "#%02X%02X%02X" % v25_world.layer(band).hue
        for key in keys:
            palette[key] = {"albedo": hue, "unshaded": True,
                            "no_fog": True}
    return {
        "id": v25_world.marker(parent),
        "title": "Marker over %s (diagnostic)" % parent,
        "family": "diagnostic",
        "summary": (
            "%s with every world surface painted the flat hue of its depth "
            "band, so a render of it can be segmented by depth" % parent
        ),
        "extends": parent,
        "palette": palette,
    }


MARKERS = [_marker(one) for one in
           ["aurora_valley", "aurora_valley_v25a", "aurora_valley_v25b",
            "aurora_valley_v25c"]]

PROFILES = [BASE, VARIANT_A, VARIANT_B, VARIANT_C] + MARKERS
IDS = [one["id"] for one in PROFILES]


def write() -> list[str]:
    written: list[str] = []
    for profile in PROFILES:
        path = os.path.join(PROFILE_DIR, f"{profile['id']}.json")
        text = json.dumps(profile, indent=2) + "\n"
        old = ""
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                old = handle.read()
        if old != text:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            written.append(path)
    index_path = os.path.join(PROFILE_DIR, "index.json")
    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)
    changed = False
    for one in IDS:
        if one not in index["profiles"]:
            index["profiles"].append(one)
            changed = True
    if changed:
        with open(index_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(index, indent=2) + "\n")
        written.append(index_path)
    return written


def camera_path(race: str, preview: str, spacing: float = 4.0) -> str:
    """Re-derive `CAMERA_PATH` from two solved camera tracks.

    Printed rather than written, because the constant is the reviewed thing:
    a keep-out that changed itself when a track file happened to be present
    would make two checkouts build two different worlds.
    """
    points: list[tuple[float, float]] = []
    for path in (race, preview):
        with open(path, encoding="utf-8") as handle:
            track = json.load(handle)
        for cut in track["cuts"]:
            for frame in cut["frames"]:
                points.append((frame[1], frame[3]))
    kept: list[tuple[float, float]] = []
    for x, z in points:
        if all((x - a) ** 2 + (z - b) ** 2 > spacing ** 2 for a, b in kept):
            kept.append((x, z))
    rows = []
    for index in range(0, len(kept), 4):
        rows.append("    " + " ".join("[%.1f, %.1f]," % one
                                      for one in kept[index:index + 4]))
    return "CAMERA_PATH = [\n" + "\n".join(rows) + "\n]"


if __name__ == "__main__":
    if "--camera-path" in sys.argv:
        base = os.path.join(PROJECT_ROOT, "output", "sloped_race_v1")
        print(camera_path(os.path.join(base, "cameras_v221_5432.json"),
                          os.path.join(base, "preview_v221_5432.json")))
        raise SystemExit(0)
    changes = write()
    for path in changes:
        print("wrote", os.path.relpath(path, PROJECT_ROOT))
    if not changes:
        print("profiles are already up to date")
    sys.exit(0)

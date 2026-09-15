"""Write the V27 contained-stage profiles from one place.

    python tools/sloped_v27_profiles.py

**Why a generator and not seven hand-written JSON files.** Three rooms are only
comparable if the things they are *not* varying are identical, and the list of
those is long: the sky, the grade, the fog, five of the eight lights, the
terrain repaint, the dressing that is switched off, the keep-out. Hand-edited
files drift - a fog density gets nudged in B and not in A, and the sheet then
compares two grades rather than two rooms. Here every shared decision is
:data:`BASE`, each concept is a delta over it, and each marker is generated
from :data:`sloped.v27_contained.MARKED` so a surface that nobody files under a
band shows up as a hole in a sheet rather than as somebody else's number.

The generated files are committed; this is how they are regenerated, and
`tests/test_sloped_v27_contained.py` checks that re-running it is a no-op.

## What the base is a delta over, and why that one

`aurora_valley_v26` - the production world - rather than `alpine_neon`, the
root. Extending the root would have meant restating the sky, the grade, the
fog, the glow, the screen-space passes and the eight-light rig before changing
any of them, and a restatement is a copy that can drift. Extending production
means the diff between what ships and what this pass proposes is literally the
diff of these files, and `sloped.environment.diff` prints it.

It also means the machine is lit identically. The base touches the five
world-layer lights and leaves `Key`, `Rim` and `ValleyBounce` exactly as V26
has them, so the machine in a contained frame is the machine in a V26 frame
under the same light - which is what makes "only the environment changed" a
property of the data rather than a claim in a report.

## The keep-out

Inherited from `aurora_valley_v25` and extended with V24's own camera path.
The inherited list was decimated from the two V22.1 tracks, and V26 renders
V24's track instead; the largest gap between a V24 camera position and the
nearest inherited point is 3.7 units, so the inherited list very nearly covers
it already. "Very nearly" is not a property to build a wall against, so the 54
decimated V24 positions are appended and the builders test against both.
"""

from __future__ import annotations

import json
import math
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sloped import environment as environment_profile  # noqa: E402
from sloped import v27_contained as v27  # noqa: E402

PROFILE_DIR = os.path.join(PROJECT_ROOT, "godot", "assets", "marble_machine",
                           "environment", "profiles")

PARENT = "aurora_valley_v26"
BASE_ID = "contained_base"


# --- the camera path V26 actually renders through ---------------------------
#
# `cameras_v24_5432.json`, decimated to four-unit spacing in plan, as a
# constant rather than as something read from a track file at generation time.
# Same reasoning as `tools/sloped_v25_profiles.CAMERA_PATH`: a keep-out that
# re-derived itself whenever a track happened to be present would make two
# checkouts build two different rooms. Regenerate with `--camera-path`.

V24_CAMERA_PATH = [
    [-25.5, -31.8], [-29.6, -30.9], [-33.1, -33.1], [-35.5, -36.6],
    [-36.6, -40.8], [-36.7, -45.0], [-28.6, -53.9], [-29.1, -49.7],
    [-29.8, -45.8], [-31.2, -42.0], [-21.6, -33.8], [-17.7, -35.2],
    [-13.5, -36.7], [-9.3, -37.6], [-5.3, -37.8], [-1.3, -37.3],
    [-0.0, -33.3], [-1.1, -29.4], [-4.9, -27.4], [-8.1, -24.8],
    [-10.8, -21.2], [-12.6, -17.4], [-16.0, -15.1], [-19.7, -13.3],
    [-23.0, -10.9], [-25.7, -7.9], [-27.6, -4.1], [-28.5, -0.0],
    [-23.6, -3.6], [-20.8, -6.4], [-8.7, -16.1], [-4.6, -17.9],
    [-0.7, -19.5], [3.2, -21.1], [7.6, -21.4], [11.5, -20.1],
    [15.2, -17.9], [18.6, -14.6], [21.5, -11.0], [23.8, -7.6],
    [25.7, -3.7], [26.9, 0.5], [27.3, 4.5], [26.9, 8.7],
    [25.5, 12.6], [23.5, 16.2], [20.9, 19.6], [17.9, 22.6],
    [14.7, 25.3], [11.3, 27.8], [7.9, 29.9], [4.2, 31.8],
    [0.4, 33.7], [-3.3, 35.3],
]


def _keepout() -> list[list[float]]:
    """The inherited list plus V24's own path, deduplicated at two units."""
    inherited = environment_profile.resolve(PARENT)["world"]["keepout"]
    out = [[float(a), float(b)] for a, b in inherited]
    for x, z in V24_CAMERA_PATH:
        if all((x - a) ** 2 + (z - b) ** 2 > 4.0 for a, b in out):
            out.append([float(x), float(z)])
    return out


# --- what every contained room agrees about ---------------------------------
#
# Eleven decisions, and each is here rather than in a concept because varying
# it would make the three sheets incomparable.

#: The outdoor world, switched off leaf by leaf. `null` erases an inherited
#: key rather than shadowing it, which is the only way a child can say "there
#: is no such thing here" instead of "there are zero of them" - and the
#: difference shows up in `environment.describe`, which counts what is
#: authored.
NO_OUTDOOR_WORLD = {
    "patches": None, "walls": None, "ridges": None, "scarps": None,
    "spires": None, "boulders": None, "anchors": None, "trees": None,
    "landmarks": None, "ravine": None, "lamps": None,
}

#: Everything `environment_builder.backdrop` builds, switched off the same way.
#: V23 measured that these cameras barely see the backdrop - four of its six
#: features moved zero pixels in twelve race moments - so removing it is close
#: to free, and what it buys is the guarantee that a mountain range cannot
#: appear through a wall that failed to build.
NO_BACKDROP = {
    "near_range": None, "ridge_range": None, "mid_range": None,
    "far_range": None, "structures": None, "dusk_band": None,
    "clouds": None, "crest_lines": None, "aurora": None, "mist": None,
}

#: The interior grade.
#:
#: **A dark sky supplies no ambient**, which V23 found by raising
#: `ambient_energy` fourfold and measuring no change at all: ambient is sampled
#: from the sky and `ambient_sky_contribution` says how much of it is, so under
#: a near-black sky every surface the key misses renders at zero however high
#: the multiplier goes. A room needs the opposite of a valley here - almost no
#: sky contribution and an explicit ambient colour - and that pairing is the
#: single most important row in this table.
GRADE = {
    "background_energy": 0.30,
    "ambient_sky_contribution": 0.08,
    "ambient_colour": "#38414F",
    "ambient_energy": 1.15,
    "exposure": 0.81,
    "white": 12.0,
    "contrast": 1.04,
    "saturation": 1.18,
}

#: A near-black neutral instead of a dusk sky. Not pure black: the enclosure is
#: not sealed, a sliver of it shows over the cornice in two shots, and a pure
#: black there reads as a render error rather than as a dark ceiling.
SKY = {
    "top": "#06080C",
    "horizon": "#0C1017",
    "curve": 0.10,
    "sky_energy": 0.55,
    "ground_bottom": "#06080B",
    "ground_horizon": "#0A0D12",
    "ground_curve": 0.22,
    "sun_angle_max": 3.0,
    "energy": 1.0,
    "sun_curve": 0.12,
}

#: Interior haze. A quarter of V26's density and almost none of its aerial
#: perspective, because a hundred and twenty units of room is not a valley: at
#: V26's 0.0038 and 0.94 the far wall washed to the sky colour, which in here
#: is near black, and the enclosure disappeared exactly where it was meant to
#: be doing its work. What is left is a small neutral lift that separates the
#: wall from the deck in front of it.
FOG = {
    "enabled": True,
    "colour": "#161C25",
    "energy": 0.62,
    "sun_scatter": 0.02,
    "density": 0.0011,
    "sky_affect": 0.10,
    "aerial_perspective": 0.22,
    "height": -96.0,
    "height_density": 0.012,
}

#: The five world-layer lights, re-aimed for an interior. `Key`, `Rim` and
#: `ValleyBounce` are **absent on purpose** - they carry cull masks that reach
#: the machine, and a pass that claims to change only the environment may not
#: touch them.
LIGHTS = {
    # A soft high key from over the wall behind the start, steep enough that a
    # horizontal deck reads and a vertical panel falls away from it.
    "WorldKey": {
        "colour": "#D3E2F4", "energy": 1.30, "specular": 0.18,
        "rotation": [-58.0, -62.0, 0.0],
        "shadow": {"enabled": True, "max_distance": 260.0,
                   "splits": [0.07, 0.22, 0.52], "blend_splits": True,
                   "bias": 0.045, "normal_bias": 1.1},
    },
    # Cool fill from the opposite side, to keep the unlit half of a rib off
    # the floor of the histogram.
    "WorldFill": {"colour": "#5E7EA6", "energy": 0.52, "specular": 0.0,
                  "rotation": [-18.0, 104.0, 0.0],
                  "shadow": {"enabled": False}},
    # The room's one warm term, raking along the wall rather than across it.
    "WorldWarm": {"colour": "#FFBE86", "energy": 0.62, "specular": 0.0,
                  "rotation": [-8.0, 32.0, 0.0],
                  "shadow": {"enabled": False}},
    # Edge separation between a panel and what is in front of it.
    "WorldRim": {"colour": "#8FC6E8", "energy": 0.44, "specular": 0.0,
                 "rotation": [-6.0, 158.0, 0.0],
                 "shadow": {"enabled": False}},
    # Up from the deck: the one light that says there is a floor down there.
    "WorldBounce": {"colour": "#3C5878", "energy": 0.55, "specular": 0.0,
                    "rotation": [24.0, 220.0, 0.0],
                    "shadow": {"enabled": False}},
}

#: The landform, repainted.
#:
#: The heightfield itself is untouched and untouchable - see GEOMETRY IS NOT
#: THEME - so the hill the course is cut into is still there in every contained
#: frame. Repainting it is what decides whether it reads as a hillside indoors
#: (which would be absurd) or as a sculpted floor the machine is installed on
#: (which is the diorama the brief is describing). Neutral, four values, and
#: the same `soft_light` shadow floor V25.2 established.
TERRAIN_PALETTE = {
    "slope_earth": {"albedo": "#2C3039", "roughness": 0.92,
                    "soft_light": "#111419", "vertex_tint": True},
    "slope_rock": {"albedo": "#23272E", "roughness": 0.92,
                   "soft_light": "#111419", "vertex_tint": True},
    "slope_cliff": {"albedo": "#1C2026", "roughness": 0.93,
                    "soft_light": "#111419", "vertex_tint": True},
    "slope_cap": {"albedo": "#262A32", "roughness": 0.91,
                  "soft_light": "#111419", "vertex_tint": True},
    "slope_scree": {"albedo": "#282C34", "roughness": 0.96},
    "slope_boulder": {"albedo": "#1A1E23", "soft_light": "#111419"},
}

#: What the outdoor dressing leaves behind. The lamp masts and the course
#: practicals stay: they are the machine's own installation and read as fitted
#: equipment in a hall as readily as on a hillside. The scrub, the ridge pylons
#: and the valley lights go, because each of the three is a statement that
#: there is an outdoors.
DRESSING = {
    "scrub": {"enabled": False},
    "pylons": {"enabled": False},
    "valley": {"enabled": False},
}


BASE = {
    "id": BASE_ID,
    "title": "Contained base - the shared spine of the V27 stage",
    "family": "contained",
    "summary": (
        "V26 with the outdoor world and the backdrop erased, the landform "
        "repainted neutral, the sky taken to near black with an explicit "
        "ambient, the haze reduced to interior scale and the five world-layer "
        "lights re-aimed. Builds no architecture of its own: a render of this "
        "profile is the empty stage, and it exists so the three concepts "
        "differ only in what they put in it."
    ),
    "extends": PARENT,
    "sky": SKY,
    "grade": GRADE,
    "fog": FOG,
    "lights": LIGHTS,
    "terrain": {"scatter": None},
    "dressing": DRESSING,
    "backdrop": NO_BACKDROP,
    "palette": TERRAIN_PALETTE,
    "world": dict(NO_OUTDOOR_WORLD, keepout=_keepout()),
}



# --- where architecture can stand on this course ----------------------------
#
# **The ground behind the race has already fallen away.** This is the finding
# that rebuilt all three concepts after their first render, and it is a fact
# about the landform rather than about any of them:
#
#     site (legal, in frame, behind the action)   ground      visible ceiling
#     behind the fork,  36 units out              -23.7            +30.2
#     behind the merge, 39 units out              -35.8             +4.4
#     behind the finish, 40 units out             -74.2             +2.6
#
# `course_terrain` fades from the racing line to `edge_y` at -82 between radius
# 58 and 94, and every place a camera can see *past* the machine is out in that
# fade. So a "recessed bay beside the track" - the form the brief's Parts M, N
# and O describe, and the form these three profiles were first authored with -
# cannot exist here: there is no ground beside the track to recess into. What
# stands at those three sites is a **tall structure rising out of a pit**, 35
# to 80 units of it, and the frame only ever shows its top.
#
# Two consequences are carried through every concept below:
#
#   * a bay's `height` is tens of units, not the ten or twenty an architectural
#     niche would be, and its `sink` is small because it stands on the fallen
#     ground rather than being cut into a hillside;
#   * the **obstacle has no bay at all**. A grid search over every position
#     within 34 units of the obstacle node found not one that is 10 from the
#     racing line, 16 from the camera path and inside the obstacle cut's
#     frustum - the camera runs along the course there and the course is the
#     whole frame. Its local identity is given by the lower wall instead, as a
#     run of three bay segments on the bearings that cut actually looks at
#     (20 to 55 degrees), which is why band 2 below carries an explicit
#     24-entry rhythm rather than a repeating one.
#
# `tools/sloped_v27_contained.py --stage envelope` prints the table these came
# from, and `--stage sites` re-runs the search.

# --- A: the premium machine hall --------------------------------------------
#
# A drum in three courses. Thirty-two segments through the full circle at
# radius 122, on an eight-step rhythm - panel, rib, panel, bay, panel, rib,
# panel, slot - so the wall repeats four times round and the eye can count it.
# Below the floor line a darker wall at 92, where the landform has fallen away
# and the finish-side cameras would otherwise see nothing but void. Behind the
# start, a third wall closer in, because the hook's one strip of visible
# background is 45 degrees wide and 120 units away.
#
# Two numbers here are measured rather than chosen:
#
#   * **the wall tops out above y = +26 at radius 122.** The highest point any
#     V26 frame reaches at that radius is +28.6, so the main course stops just
#     under it and a clerestory carries the rest - which puts the string
#     course between them at exactly the height the top of the hook frame
#     passes through, and turns the one architectural line a viewer can see in
#     that shot into a deliberate one.
#   * **the lower wall tops out at +4.** The ceiling at radius 90 on bearings
#     20 to 55 - where the obstacle cut's upper frame lands at distance - is
#     -6 to +4, so its cornice lands just inside the top of that shot.

HALL = {
    "id": "contained_hall",
    "title": "A - Premium machine hall",
    "family": "contained",
    "summary": (
        "A round graphite hall in three courses: a 32-segment drum at radius "
        "122 with a string course at +26 and a clerestory above it, a darker "
        "lower wall at 92 carrying the obstacle's three bays, a taller near "
        "wall behind the start, two deck bands and sixteen braced columns; "
        "no overhead structure, which is a measured result rather than a "
        "stylistic choice"
    ),
    "extends": BASE_ID,
    # **Every surface carries a shadow floor, and the render is what asked for
    # it.** The first build of all three concepts crushed 10 to 17 per cent of
    # every frame to luma 5 or under, against V26's 2.9 - and 89 per cent of
    # that black was the *wall*, not the sky. A chamber wall faces inward, one
    # directional key cannot reach more than half of a ring of them, and a flat
    # panel with nothing but ambient on it renders as one near-black value.
    #
    # The remedy is V25.2's, for the same diagnosis it wrote it for:
    # `soft_light` is a backlight, which adds a term proportional to 1 - N.L
    # and therefore lands exactly and only on the faces turned away from the
    # key; `floor_lift` is a small constant emission under the surface, a
    # lifted black point rather than a glow. A sixth light would have raised
    # the whole room and given the faces pointing at *it* a second key.
    "palette": {
        "hall_panel": {"albedo": "#242830", "roughness": 0.60,
                       "soft_light": "#2A3441", "floor_lift": "#161C26"},
        "hall_panel_dark": {"albedo": "#151920", "roughness": 0.88,
                            "soft_light": "#1E2632", "floor_lift": "#11161E"},
        "hall_rib": {"albedo": "#2E343E", "roughness": 0.42,
                     "soft_light": "#232C3A", "floor_lift": "#141A23"},
        "hall_trim": {"albedo": "#525A65", "roughness": 0.38,
                      "soft_light": "#2E3745", "floor_lift": "#181E2A"},
        "hall_deck": {"albedo": "#2E333C", "roughness": 0.90,
                      "soft_light": "#26303C", "floor_lift": "#13181F"},
        "hall_deck_dark": {"albedo": "#171B22", "roughness": 0.93,
                           "floor_lift": "#0F131A"},
        "hall_beam": {"albedo": "#1C2028", "roughness": 0.86,
                      "soft_light": "#1E2632", "floor_lift": "#11161E"},
        # Dark glass, as an opaque gloss rather than as transparency: there is
        # nothing behind it to see, and an alpha pane here would cost sorting
        # against every transparent guard on the machine for that nothing.
        "hall_glass": {"albedo": "#0E1219", "roughness": 0.10,
                       "soft_light": "#1A2230", "floor_lift": "#0C1018"},
        "lit_hall_warm": {"emission": "#FFC489", "energy": 1.55},
        "lit_hall_cool": {"emission": "#9FD4FF", "energy": 1.05},
    },
    "world": {
        "deck": {
            "rings": [
                {"inner": 88.0, "outer": 124.0, "y": -80.0, "thickness": 4.0,
                 "facets": 28, "material": "hall_deck", "fillet": 0.5},
                {"inner": 122.0, "outer": 154.0, "y": -74.0, "thickness": 5.0,
                 "facets": 32, "material": "hall_deck_dark", "fillet": 0.5},
            ],
            # A landing under the finish. Authored with both guards off, and
            # that is the whole reason the fields exist: a floor plate under
            # the racing line is exactly what rejection sampling is meant to
            # refuse, and it is also what Part O asks for.
            "pads": [
                {"at": [23.0, 41.0], "size": [40.0, 1.6, 34.0], "sink": 1.1,
                 "bearing": 28.0, "material": "hall_deck",
                 "clearance": 0.0, "keepout": 0.0},
            ],
            "clearance": 0.0, "keepout": 0.0,
        },
        "shell": {
            "bands": [
                {
                    # The main course. Stops at +26 so the string course above
                    # it is inside the frame rather than over it.
                    "count": 32, "bearing_from": 0.0, "bearing_step": 11.25,
                    "radius": 122.0, "height": 126.0, "foot": -100.0,
                    "thickness": 6.0, "fill": 0.995, "batter": 2.0,
                    "fillet": 0.7, "keepout": 40.0,
                    # Four dark-glass segments in thirty-two: the brief's
                    # "occasional glass or translucent panels", and the count
                    # is what makes it occasional. They are in the *main*
                    # course rather than the clerestory because the clerestory
                    # is mostly above the visible ceiling (§4) - a glazed
                    # upper storey would have been an idea nobody could see.
                    "pattern": ["panel", "rib", "glass", "bay",
                                "panel", "rib", "panel", "slot"],
                    "material": "hall_panel",
                    "bay_depth": 7.0,
                    "glass": {"margin": 3.5, "span": 0.30, "at": 0.72,
                              "material": "hall_glass"},
                    "rib": {"count": 1, "width": 3.4, "depth": 2.6,
                            "material": "hall_rib"},
                    "bay": {"jamb": 4.5, "head": 5.0, "sill": 34.0,
                            "opening": 0.40, "lift": 0.34,
                            "material": "hall_panel",
                            "strip": {"width": 0.66, "height": 1.6,
                                      "depth": 0.7, "at": 0.95,
                                      "material": "lit_hall_warm"}},
                    "slot": {"at": 0.74, "width": 0.66, "height": 1.8,
                             "depth": 0.8, "material": "lit_hall_cool"},
                    "plinth": {"height": 3.2, "depth": 1.6, "at": 0.0,
                               "material": "hall_trim"},
                },
                {
                    # The clerestory, and its plinth is the string course:
                    # one continuous light-value band at +26, which is the
                    # height the top of the hook frame passes through at this
                    # radius. The rhythm is alternating, so the upper storey
                    # is a row of slots rather than a second wall.
                    "count": 32, "bearing_from": 0.0, "bearing_step": 11.25,
                    "radius": 122.0, "height": 30.0, "foot": 26.0,
                    "thickness": 6.0, "fill": 0.995, "fillet": 0.7,
                    "keepout": 40.0,
                    "pattern": ["panel", "slot"],
                    "material": "hall_panel",
                    "slot": {"at": 0.46, "width": 0.62, "height": 2.2,
                             "depth": 0.8, "material": "lit_hall_cool"},
                    "plinth": {"height": 4.2, "depth": 2.6, "at": 0.0,
                               "material": "hall_trim"},
                    "cornice": {"height": 4.0, "depth": 2.4, "at": 1.0,
                                "material": "hall_trim"},
                },
                {
                    # The lower wall, and the one the obstacle is read
                    # against. The rhythm is written out in full because
                    # three of its segments are doing a named job: indices 1,
                    # 2 and 3 sit at bearings 22.5, 37.5 and 52.5, which is
                    # where the obstacle cut's upper frame lands at distance,
                    # and they are that section's local identity.
                    "count": 24, "bearing_from": 7.5, "bearing_step": 15.0,
                    "radius": 92.0, "height": 100.0, "foot": -96.0,
                    "thickness": 5.0, "fill": 0.99, "fillet": 0.6,
                    "keepout": 18.0, "bay_depth": 6.0,
                    "pattern": ["rib", "bay", "bay", "bay", "rib", "panel",
                                "slot", "panel", "rib", "panel", "panel",
                                "slot", "rib", "panel", "panel", "panel",
                                "rib", "panel", "slot", "panel", "rib",
                                "panel", "panel", "panel"],
                    "material": "hall_panel_dark",
                    "rib": {"count": 1, "width": 3.0, "depth": 2.2,
                            "material": "hall_rib"},
                    "bay": {"jamb": 4.0, "head": 4.0, "sill": 26.0,
                            "opening": 0.30, "lift": 0.62,
                            "material": "hall_panel_dark",
                            "strip": {"width": 0.6, "height": 1.4,
                                      "depth": 0.7, "at": 0.92,
                                      "material": "lit_hall_warm"}},
                    "slot": {"at": 0.86, "width": 0.6, "height": 1.4,
                             "depth": 0.7, "material": "lit_hall_cool"},
                    "cornice": {"height": 3.0, "depth": 1.6, "at": 1.0,
                                "material": "hall_trim"},
                },
                {
                    # **The hook's backdrop.** The start sits in a cut on the
                    # uphill side and the hill behind it is +40 at radius 60,
                    # so the only background the opening shot has is the strip
                    # above that ridge: bearings 150 to 210, and a wall at 122
                    # is 120 units away in it. This one is at 90 and tops out
                    # at +38 - a near, tall, lit surface where there was sky -
                    # and it is the single change that makes frame 0 look like
                    # a room rather than a hillside at night.
                    "count": 6, "bearing_from": 150.0, "bearing_step": 12.0,
                    "radius": 90.0, "height": 134.0, "foot": -96.0,
                    "thickness": 6.0, "fill": 1.0, "fillet": 0.7,
                    "keepout": 20.0,
                    "pattern": ["rib", "panel", "bay", "panel", "rib",
                                "panel"],
                    "material": "hall_panel",
                    "bay_depth": 7.0,
                    "rib": {"count": 1, "width": 3.6, "depth": 2.8,
                            "material": "hall_rib"},
                    "bay": {"jamb": 5.0, "head": 5.0, "sill": 86.0,
                            "opening": 0.24, "lift": 0.66,
                            "material": "hall_panel",
                            "strip": {"width": 0.66, "height": 1.8,
                                      "depth": 0.8, "at": 0.94,
                                      "material": "lit_hall_warm"}},
                    "cornice": {"height": 4.0, "depth": 2.4, "at": 1.0,
                                "material": "hall_trim"},
                },
            ],
        },
        # **Two rings, and the second one is a correction.** The first build
        # gave A one ring of sixteen columns at radius 80 and 58 units tall,
        # and the marker segmentation measured its structure band at 0 to 5
        # per cent of every frame against V26's 18 to 50. A stage with a wall
        # and a floor and nothing between them is two layers, not three, and
        # Part B of the brief asks for three.
        #
        # What was wrong was height before it was count: at radius 80 the
        # ground has already fallen to between -45 and -72, so a 58-unit
        # column tops out below the visible ceiling over most of the compass
        # and is simply not in shot. 82 puts its head in frame. The inner ring
        # at 64 is the one that carries the parallax - it is the nearest thing
        # in this stage that is not the machine - and its keep-out is the
        # tightest here because that is exactly what makes it useful.
        "pylons": {
            "bands": [
                {
                    "count": 16, "bearing_from": 8.0, "bearing_step": 22.5,
                    "radius": 80.0, "height": 82.0, "width": 3.6,
                    "depth": 3.6, "sink": 2.5, "clearance": 16.0,
                    "keepout": 26.0, "fillet": 0.4, "material": "hall_rib",
                    "cap": {"spread": 1.8, "height": 1.8,
                            "material": "hall_rib"},
                    "brace": {"stock": 0.8, "at": 0.86, "max_span": 42.0,
                              "material": "hall_beam"},
                },
                {
                    "count": 12, "bearing_from": 20.0, "bearing_step": 30.0,
                    "radius": 64.0, "height": 54.0, "width": 3.0,
                    "depth": 3.0, "sink": 2.0, "clearance": 18.0,
                    "keepout": 24.0, "fillet": 0.4, "material": "hall_rib",
                    "cap": {"spread": 1.7, "height": 1.4,
                            "material": "hall_rib"},
                },
            ],
        },
        # **A has no overhead structure, and that is a measured result rather
        # than a stylistic choice.** Part H asks whether partial overhead
        # architecture improves containment here. Three placements were built
        # and rendered and all three failed, for two different reasons that
        # between them close the question for this camera track:
        #
        #   over the machine      invisible. The top edge of every V26 frame
        #                         is at least 4.7 degrees *below* horizontal
        #                         - elevation 30 to 54, vertical field 34 to 36
        #                         - so nothing above a camera's own eye height
        #                         is ever in shot, at any radius.
        #   over the low course   a bar across the action. Where the track has
        #                         descended enough for an overhead member to be
        #                         in frame, the headroom between the course and
        #                         the top of the frame is 2.6 units at the
        #                         finish and 4.4 at the merge. The second
        #                         attempt sat at +9 over the finish run and cut
        #                         the FINISH board in half.
        #
        # The builder stays - it is part of the stage and a course photographed
        # from lower cameras will want it - and concept C carries the one
        # placement that does work: a catwalk out at radius 60 to 100 on the
        # left wall, which is in frame, clear of the lens and above nothing.
        # The three sites the search found - see "where architecture can
        # stand" above. All three stand on ground that has already fallen 24
        # to 74 units below the racing line, so every height here is tens of
        # units and only the top of each form is ever in frame. The obstacle
        # has no entry: no legal position near it is in that cut's frustum.
        "bays": {
            "clearance": 9.0, "keepout": 14.0,
            "sites": {
                "split": {
                    "node": "split", "offset": [36.0, 6.0], "bearing": 80.0,
                    "kind": "portal", "width": 34.0, "height": 58.0,
                    "thickness": 3.4, "sink": 2.0, "jamb": 5.0,
                    "head": 5.0, "fillet": 0.6,
                    "material": "hall_panel", "trim": "hall_trim",
                    "wing": {"width": 20.0, "spread": 34.0, "span": 0.72,
                             "reach": 0.92, "material": "hall_panel_dark"},
                },
                "merge": {
                    "node": "merge", "offset": [8.0, 38.0], "bearing": 12.0,
                    "kind": "backing", "width": 46.0, "height": 46.0,
                    "thickness": 3.4, "sink": 2.0,
                    "fillet": 0.6, "material": "hall_panel_dark",
                    "trim": "hall_trim",
                    "strip": {"width": 0.62, "height": 1.4, "at": 0.90,
                              "material": "lit_hall_cool"},
                },
                "finish": {
                    "node": "finish", "offset": [32.0, 20.0], "bearing": 58.0,
                    "kind": "frame", "width": 40.0, "height": 84.0,
                    "thickness": 3.4, "sink": 2.0, "jamb": 5.0,
                    "head": 5.0, "sill": 3.0, "fillet": 0.6,
                    "material": "hall_panel", "trim": "hall_trim",
                    "strip": {"width": 0.70, "height": 1.6, "at": 0.90,
                              "material": "lit_hall_warm"},
                },
            },
        },
    },
}


# --- B: the toy diorama chamber ---------------------------------------------
#
# Closer, lower, rounder and with far fewer pieces in it. Eighteen segments on
# a two-step radius cycle, so the plan is a scalloped ring rather than a drum;
# the fillet is trebled, the cornice and plinth are heavy, and the rhythm is
# two big niches to one rib rather than A's eight-step architectural metre.
#
# The landform stands on a broad display platform - a deck band at -48 with its
# own skirt wall under it - which is the collector-set read the brief asks for:
# an object presented on a plinth rather than a place you are standing in.

DIORAMA = {
    "id": "diorama_chamber",
    "title": "B - Toy diorama chamber",
    "family": "contained",
    "summary": (
        "A lobed display chamber: eighteen segments alternating radius 104 "
        "and 113 with large sculpted niches and a heavy cornice, a broad "
        "platform at -48 with its own skirt wall, a taller lobed wall behind "
        "the start, eight low display posts and no overhead structure at all"
    ),
    "extends": BASE_ID,
    # Warmer and one value lighter than A, because a collector-set wall is a
    # moulded surface rather than a fabricated one, and the eye reads moulded
    # from the value of the mid-tone before it reads it from form. The shadow
    # floors are A's arrangement at B's own values - see the note there.
    "palette": {
        "hall_panel": {"albedo": "#2B2E35", "roughness": 0.68,
                       "soft_light": "#2E343E", "floor_lift": "#191D25"},
        "hall_panel_dark": {"albedo": "#1B1E25", "roughness": 0.86,
                            "soft_light": "#222730", "floor_lift": "#13161D"},
        "hall_rib": {"albedo": "#353A43", "roughness": 0.52,
                     "soft_light": "#272D38", "floor_lift": "#161A22"},
        "hall_trim": {"albedo": "#5B626C", "roughness": 0.44,
                      "soft_light": "#333A46", "floor_lift": "#1A2029"},
        "hall_deck": {"albedo": "#343942", "roughness": 0.88,
                      "soft_light": "#2A303B", "floor_lift": "#161A21"},
        "hall_deck_dark": {"albedo": "#1D2128", "roughness": 0.92,
                           "floor_lift": "#11141A"},
        "hall_beam": {"albedo": "#20242B", "roughness": 0.86,
                      "soft_light": "#222730", "floor_lift": "#13161D"},
        "lit_hall_warm": {"emission": "#FFCB98", "energy": 1.35},
        "lit_hall_cool": {"emission": "#A8D8FF", "energy": 0.95},
    },
    "world": {
        "deck": {
            "rings": [
                {"inner": 78.0, "outer": 114.0, "y": -48.0, "thickness": 6.0,
                 "facets": 18, "material": "hall_deck", "fillet": 1.4},
                {"inner": 112.0, "outer": 152.0, "y": -74.0, "thickness": 6.0,
                 "facets": 24, "material": "hall_deck_dark", "fillet": 1.0},
            ],
            "pads": [
                {"at": [23.0, 41.0], "size": [42.0, 2.0, 36.0], "sink": 1.2,
                 "bearing": 28.0, "material": "hall_deck", "fillet": 1.2,
                 "clearance": 0.0, "keepout": 0.0},
            ],
            "clearance": 0.0, "keepout": 0.0,
        },
        "shell": {
            "bands": [
                {
                    "count": 18, "bearing_from": 0.0, "bearing_step": 20.0,
                    "radius": 104.0, "radius_step": 9.0, "radius_cycle": 2,
                    "height": 142.0, "foot": -96.0,
                    "thickness": 8.0, "fill": 1.04, "fillet": 1.8,
                    "keepout": 36.0,
                    "pattern": ["bay", "panel", "bay", "rib"],
                    "material": "hall_panel",
                    "bay_depth": 9.0,
                    "rib": {"count": 1, "width": 6.0, "depth": 3.4,
                            "material": "hall_rib"},
                    "bay": {"jamb": 6.5, "head": 7.0, "sill": 62.0,
                            "opening": 0.34, "lift": 0.46,
                            "material": "hall_panel_dark",
                            "strip": {"width": 0.7, "height": 2.0,
                                      "depth": 0.9, "at": 0.96,
                                      "material": "lit_hall_warm"}},
                    "cornice": {"height": 5.5, "depth": 3.4, "at": 1.0,
                                "material": "hall_trim"},
                    "plinth": {"height": 5.0, "depth": 2.8, "at": 0.0,
                               "material": "hall_trim"},
                },
                {
                    # The platform's skirt: what makes the deck band read as a
                    # plinth the landform stands on rather than as a shelf
                    # floating in front of the wall.
                    #
                    # Its keep-out is 10 rather than the 15 it was authored
                    # with, and that is a fix rather than a relaxation: at 15
                    # one segment out of eighteen was rejected, which does not
                    # remove a skirt, it removes a *tooth* from one - a gap in
                    # a continuous band reads as a build error where a whole
                    # missing band would have read as a choice.
                    "count": 18, "bearing_from": 10.0, "bearing_step": 20.0,
                    "radius": 79.0, "height": 48.0, "foot": -94.0,
                    "thickness": 4.0, "fill": 1.02, "fillet": 1.0,
                    "keepout": 10.0,
                    "pattern": ["panel"],
                    "material": "hall_panel_dark",
                    "cornice": {"height": 2.4, "depth": 1.8, "at": 1.0,
                                "material": "hall_trim"},
                },
                {
                    # The hook's backdrop, on B's own plan: five wide lobed
                    # segments behind the start, the same site A uses and the
                    # same reason.
                    "count": 5, "bearing_from": 152.0, "bearing_step": 15.0,
                    "radius": 90.0, "radius_step": 6.0, "radius_cycle": 2,
                    "height": 136.0, "foot": -96.0,
                    "thickness": 8.0, "fill": 1.05, "fillet": 1.8,
                    "keepout": 20.0,
                    "pattern": ["bay", "rib", "bay", "panel", "rib"],
                    "material": "hall_panel",
                    "bay_depth": 9.0,
                    "rib": {"count": 1, "width": 7.0, "depth": 3.8,
                            "material": "hall_rib"},
                    "bay": {"jamb": 7.0, "head": 7.0, "sill": 94.0,
                            "opening": 0.22, "lift": 0.68,
                            "material": "hall_panel_dark",
                            "strip": {"width": 0.7, "height": 2.0,
                                      "depth": 0.9, "at": 0.96,
                                      "material": "lit_hall_warm"}},
                    "cornice": {"height": 5.5, "depth": 3.4, "at": 1.0,
                                "material": "hall_trim"},
                },
            ],
        },
        # Display columns rather than the eight low bollards this concept was
        # first authored with, and for the reason A grew a second ring: at 26
        # units tall on ground that has fallen 40, they measured at exactly
        # zero per cent of every frame. These are B's own form - fewer,
        # wider, heavily filleted, capped - at a height that reaches the
        # picture.
        "pylons": {
            "bands": [
                {
                    "count": 10, "bearing_from": 18.0, "bearing_step": 36.0,
                    "radius": 70.0, "height": 74.0, "width": 6.4,
                    "depth": 6.4, "sink": 2.0, "clearance": 17.0,
                    "keepout": 25.0, "fillet": 1.6, "material": "hall_rib",
                    "cap": {"spread": 1.5, "height": 3.0,
                            "material": "hall_rib"},
                },
                {
                    "count": 6, "bearing_from": 40.0, "bearing_step": 60.0,
                    "radius": 60.0, "height": 44.0, "width": 5.2,
                    "depth": 5.2, "sink": 2.0, "clearance": 19.0,
                    "keepout": 24.0, "fillet": 1.6, "material": "hall_rib",
                    "cap": {"spread": 1.5, "height": 2.6,
                            "material": "hall_rib"},
                },
            ],
        },
        "bays": {
            "clearance": 9.0, "keepout": 14.0,
            "sites": {
                "split": {
                    "node": "split", "offset": [36.0, 6.0], "bearing": 80.0,
                    "kind": "portal", "width": 34.0, "height": 58.0,
                    "thickness": 4.6, "sink": 2.0, "jamb": 7.0,
                    "head": 6.0, "fillet": 1.6,
                    "material": "hall_panel", "trim": "hall_trim",
                    "wing": {"width": 20.0, "spread": 34.0, "span": 0.72,
                             "reach": 0.92, "material": "hall_panel_dark"},
                },
                "merge": {
                    "node": "merge", "offset": [8.0, 38.0], "bearing": 12.0,
                    "kind": "backing", "width": 46.0, "height": 46.0,
                    "thickness": 4.6, "sink": 2.0,
                    "fillet": 1.6, "material": "hall_panel_dark",
                    "trim": "hall_trim",
                    "strip": {"width": 0.62, "height": 1.4, "at": 0.90,
                              "material": "lit_hall_cool"},
                },
                "finish": {
                    "node": "finish", "offset": [32.0, 20.0], "bearing": 58.0,
                    "kind": "frame", "width": 40.0, "height": 84.0,
                    "thickness": 4.6, "sink": 2.0, "jamb": 7.0,
                    "head": 6.0, "sill": 3.0, "fillet": 1.6,
                    "material": "hall_panel", "trim": "hall_trim",
                    "strip": {"width": 0.70, "height": 1.6, "at": 0.90,
                              "material": "lit_hall_warm"},
                },
            },
        },
    },
}


# --- C: the enclosed industrial canyon --------------------------------------
#
# Two tall slabs at radius 88 facing each other across the course, a deep back
# wall at 140, a twelve-leg braced truss line and two bridge groups. The only
# concept whose enclosure is not a ring: the cameras only ever look across
# bearings 315 to 150, and this is the one that takes that literally in its
# near wall while keeping a full ring further out.
#
# Its ambient is lifted a tenth over the shared base. That is not a repaint: at
# the base value the branch frame measured a mean luma of 21 against A's 34,
# because C's own surfaces are the darkest of the three *and* its near wall
# stands closest, so it shadows the most. The lift restores the shared
# exposure rather than changing it.

INDUSTRIAL = {
    "id": "industrial_chamber",
    "title": "C - Enclosed industrial canyon",
    "family": "contained",
    "summary": (
        "A semi-closed mechanical chamber: two slab walls at radius 88 "
        "topping out at +80, a plain back wall at 140, a twelve-leg braced "
        "truss line, two bridge groups over the merge and the finish, a "
        "grated service deck and a dark shaft floor"
    ),
    "extends": BASE_ID,
    "grade": {"ambient_energy": 1.28},
    # The darkest family of the three, and therefore the one that needed the
    # largest shadow floors: C's first build crushed 40.5 per cent of the
    # payoff frame to luma 5 or under. See the note on A's palette.
    "palette": {
        "hall_panel": {"albedo": "#1F232A", "roughness": 0.78,
                       "soft_light": "#2A3340", "floor_lift": "#171C25"},
        "hall_panel_dark": {"albedo": "#111419", "roughness": 0.90,
                            "soft_light": "#1F2731", "floor_lift": "#12161E"},
        "hall_rib": {"albedo": "#2A3038", "roughness": 0.50,
                     "soft_light": "#242D3A", "floor_lift": "#151A23"},
        "hall_trim": {"albedo": "#495058", "roughness": 0.46,
                      "soft_light": "#2E3745", "floor_lift": "#191F2A"},
        "hall_deck": {"albedo": "#272C33", "roughness": 0.94,
                      "soft_light": "#262F3B", "floor_lift": "#13181F"},
        "hall_deck_dark": {"albedo": "#121519", "roughness": 0.95,
                           "floor_lift": "#10141A"},
        "hall_grate": {"albedo": "#232830", "roughness": 0.97,
                       "soft_light": "#232B36", "floor_lift": "#141920"},
        "hall_beam": {"albedo": "#181C22", "roughness": 0.88,
                      "soft_light": "#1F2731", "floor_lift": "#12161E"},
        "lit_hall_warm": {"emission": "#FFB877", "energy": 1.75},
        "lit_hall_cool": {"emission": "#8FC8FF", "energy": 1.25},
    },
    "world": {
        "deck": {
            "rings": [
                {"inner": 84.0, "outer": 116.0, "y": -70.0, "thickness": 3.0,
                 "facets": 30, "material": "hall_grate", "fillet": 0.3},
                {"inner": 114.0, "outer": 158.0, "y": -80.0, "thickness": 5.0,
                 "facets": 34, "material": "hall_deck_dark", "fillet": 0.4},
            ],
            "pads": [
                {"at": [23.0, 41.0], "size": [38.0, 1.4, 32.0], "sink": 1.0,
                 "bearing": 28.0, "material": "hall_grate",
                 "clearance": 0.0, "keepout": 0.0},
            ],
            "clearance": 0.0, "keepout": 0.0,
        },
        "shell": {
            "bands": [
                {
                    # The left slab: bearings 66 to 162, the wall the descent,
                    # the obstacle, the fork and the start are all read
                    # against. Extended past 150 on the second pass, because
                    # the hook's background is at 150 to 210 and the first
                    # build walled only as far as the last bearing the *race*
                    # cameras use.
                    "count": 9, "bearing_from": 66.0, "bearing_step": 12.0,
                    "radius": 88.0, "height": 180.0, "foot": -100.0,
                    "thickness": 8.0, "fill": 1.01, "fillet": 0.5,
                    "keepout": 22.0,
                    "pattern": ["panel", "rib", "panel", "slot"],
                    "material": "hall_panel",
                    "rib": {"count": 2, "width": 2.6, "depth": 3.6,
                            "material": "hall_rib"},
                    "slot": {"at": 0.52, "width": 0.6, "height": 1.4,
                             "depth": 0.7, "material": "lit_hall_warm"},
                    "plinth": {"height": 4.0, "depth": 2.0, "at": 0.0,
                               "material": "hall_trim"},
                },
                {
                    # Behind the start.
                    "count": 4, "bearing_from": 174.0, "bearing_step": 12.0,
                    "radius": 88.0, "height": 180.0, "foot": -100.0,
                    "thickness": 8.0, "fill": 1.01, "fillet": 0.5,
                    "keepout": 18.0,
                    "pattern": ["rib", "panel", "slot", "panel"],
                    "material": "hall_panel",
                    "rib": {"count": 2, "width": 2.6, "depth": 3.6,
                            "material": "hall_rib"},
                    "slot": {"at": 0.66, "width": 0.6, "height": 1.4,
                             "depth": 0.7, "material": "lit_hall_warm"},
                    "plinth": {"height": 4.0, "depth": 2.0, "at": 0.0,
                               "material": "hall_trim"},
                },
                {
                    # The right slab: bearings 306 to 354, behind the finish.
                    "count": 5, "bearing_from": 306.0, "bearing_step": 12.0,
                    "radius": 88.0, "height": 180.0, "foot": -100.0,
                    "thickness": 8.0, "fill": 1.01, "fillet": 0.5,
                    "keepout": 22.0,
                    "pattern": ["rib", "panel", "slot", "panel"],
                    "material": "hall_panel",
                    "rib": {"count": 2, "width": 2.6, "depth": 3.6,
                            "material": "hall_rib"},
                    "slot": {"at": 0.36, "width": 0.6, "height": 1.4,
                             "depth": 0.7, "material": "lit_hall_warm"},
                    "plinth": {"height": 4.0, "depth": 2.0, "at": 0.0,
                               "material": "hall_trim"},
                },
                {
                    # The back of the chamber, plain and far. A full ring
                    # rather than an arc, because the saving from walling only
                    # the seen arc is worth measuring but not worth shipping a
                    # stage that cannot host a second camera track.
                    "count": 30, "bearing_from": 0.0, "bearing_step": 12.0,
                    "radius": 140.0, "height": 142.0, "foot": -100.0,
                    "thickness": 6.0, "fill": 0.99, "fillet": 0.5,
                    "keepout": 40.0,
                    "pattern": ["panel", "panel", "rib"],
                    "material": "hall_panel_dark",
                    "rib": {"count": 1, "width": 4.0, "depth": 2.4,
                            "material": "hall_rib"},
                    "cornice": {"height": 3.4, "depth": 2.0, "at": 1.0,
                                "material": "hall_trim"},
                },
            ],
        },
        "pylons": {
            "count": 12, "bearing_from": 14.0, "bearing_step": 30.0,
            "radius": 76.0, "height": 76.0, "width": 2.8, "depth": 2.8,
            "sink": 2.0, "clearance": 16.0, "keepout": 26.0, "fillet": 0.3,
            "material": "hall_rib",
            "cap": {"spread": 2.2, "height": 1.2, "material": "hall_rib"},
            "brace": {"stock": 1.0, "at": 0.62, "max_span": 46.0,
                      "material": "hall_beam"},
            "lamp": {"width": 0.6, "height": 1.2, "depth": 0.5, "at": 0.80,
                     "material": "lit_hall_warm"},
        },
        # The one overhead placement on this course that reads. Three members
        # on the left wall's own bearing, spanning radius 56 to 100 at y = +24
        # - inside the measured ceiling of about +30 on bearings 90 to 120, out
        # past the far end of the camera path, and above nothing at all, since
        # the course never gets beyond radius 47. They cross in front of the
        # slab wall rather than over the machine, which is what a catwalk in a
        # plant looks like anyway.
        "canopy": {
            "ribs": {
                "count": 3, "centre": [78.0, -21.0], "bearing": 14.0,
                "pitch": 22.0, "length": 70.0, "y": 24.0, "width": 4.4,
                "depth": 3.4, "keepout": 30.0, "material": "hall_beam",
                "hanger": {"reach": 8.0, "at": 0.30, "material": "hall_rib"},
                "lamp": {"width": 0.5, "height": 0.7, "span": 0.42,
                         "material": "lit_hall_cool", "skip": [1]},
            },
        },
        "bays": {
            "clearance": 9.0, "keepout": 14.0,
            "sites": {
                "split": {
                    "node": "split", "offset": [36.0, 6.0], "bearing": 80.0,
                    "kind": "portal", "width": 34.0, "height": 58.0,
                    "thickness": 3.0, "sink": 2.0, "jamb": 3.6,
                    "head": 3.0, "fillet": 0.4,
                    "material": "hall_panel", "trim": "hall_rib",
                    "wing": {"width": 20.0, "spread": 34.0, "span": 0.72,
                             "reach": 0.92, "material": "hall_panel_dark"},
                },
                "merge": {
                    "node": "merge", "offset": [8.0, 38.0], "bearing": 12.0,
                    "kind": "backing", "width": 46.0, "height": 46.0,
                    "thickness": 3.0, "sink": 2.0,
                    "fillet": 0.4, "material": "hall_panel_dark",
                    "trim": "hall_rib",
                    "strip": {"width": 0.62, "height": 1.4, "at": 0.90,
                              "material": "lit_hall_cool"},
                },
                "finish": {
                    "node": "finish", "offset": [32.0, 20.0], "bearing": 58.0,
                    "kind": "frame", "width": 40.0, "height": 84.0,
                    "thickness": 3.0, "sink": 2.0, "jamb": 3.6,
                    "head": 3.0, "sill": 3.0, "fillet": 0.4,
                    "material": "hall_panel", "trim": "hall_trim",
                    "strip": {"width": 0.70, "height": 1.6, "at": 0.90,
                              "material": "lit_hall_warm"},
                },
            },
        },
    },
}

CONCEPTS = [HALL, DIORAMA, INDUSTRIAL]


# --- the diagnostic twins ---------------------------------------------------


def _marker(parent: str, marker_id: str) -> dict:
    palette: dict = {}
    for band, keys in v27.marked_for(parent).items():
        hue = "#%02X%02X%02X" % v27.layer(band).hue
        for key in keys:
            palette[key] = {"albedo": hue, "unshaded": True, "no_fog": True}
    return {
        "id": marker_id,
        "title": "Marker over %s (diagnostic)" % parent,
        "family": "diagnostic",
        "summary": (
            "%s with every stage surface painted the flat hue of its depth "
            "band, so a render of it can be segmented by depth" % parent
        ),
        "extends": parent,
        "palette": palette,
    }


MARKERS = [_marker(parent, marker_id)
           for parent, marker_id in v27.MARKERS.items()]

PROFILES = [BASE] + CONCEPTS + MARKERS
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


def camera_path(track: str, spacing: float = 4.0) -> str:
    """Re-derive :data:`V24_CAMERA_PATH` from a solved track.

    Printed rather than written, because the constant is the reviewed thing.
    """
    with open(track, encoding="utf-8") as handle:
        solved = json.load(handle)
    kept: list[tuple[float, float]] = []
    for cut in solved["cuts"]:
        for frame in cut["frames"]:
            x, z = frame[1], frame[3]
            if all((x - a) ** 2 + (z - b) ** 2 > spacing ** 2
                   for a, b in kept):
                kept.append((x, z))
    rows = []
    for index in range(0, len(kept), 4):
        rows.append("    " + " ".join("[%.1f, %.1f]," % one
                                      for one in kept[index:index + 4]))
    return "V24_CAMERA_PATH = [\n" + "\n".join(rows) + "\n]"


if __name__ == "__main__":
    if "--camera-path" in sys.argv:
        print(camera_path(os.path.join(PROJECT_ROOT, "output",
                                       "sloped_race_v1",
                                       "cameras_v24_5432.json")))
        raise SystemExit(0)
    for path in write():
        print("wrote", os.path.relpath(path, PROJECT_ROOT))

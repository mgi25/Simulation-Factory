"""V25.2: the final world-lookdev profile, written from one source.

    python tools/sloped_v252_profiles.py           # write the JSON
    python tools/sloped_v252_profiles.py --check   # fail if it is stale

One profile and one marker:

    aurora_valley_v252     the lookdev pass
    _marker_v252           the same, painted flat by depth band

**This one really is a delta.** `aurora_valley_v251` restated the whole `world`
section because its brief was "B's layout, different forms", and a *target* is
something to state rather than to inherit by accident. This brief is the
opposite: the layout, the density, the sites, the counts, the kit assignments
and the camera keep-out are all V25.1's and none of them is being renegotiated.
So this file extends `aurora_valley_v251` and carries only what the five jobs
move - the shading response, the hero silhouettes, the warmth, the vegetation
forms and two compositions.

Everything in here is render-only. No collider, no height field, no physics, no
camera, no replay, no seed. See `docs/sloped_race_v252_world.md`.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tools import sloped_v25_profiles as v25  # noqa: E402
from tools import sloped_v251_profiles as v251  # noqa: E402

PROFILE_DIR = v25.PROFILE_DIR


# --- A: the shading response ------------------------------------------------
#
# The pass's first job and the one the other four stand on.
#
# **What is actually wrong.** V25.1's own section 12 measured it and then
# correctly refused to explain it away: the midground ridge band went from
# 22.6% of its pixels under grey 12 to **42.2%**, and its median grey fell from
# 17 to 14.3, while every other band got lighter. Three lighting fixes were
# swept and falsified. The conclusion it reached - that the tail is intrinsic
# to flat shading - is right about *lighting* and is not the end of the
# argument, because two of the three terms that decide a pixel's value were
# never touched:
#
#   1. **the normal**, which V25.1 fixed at one per face by construction, and
#   2. **the albedo**, which is one constant per material over a mass a
#      hundred units tall.
#
# So the fix is not another light. It is `temper` and `shade` in
# `world_rock.gd`, plus one material term that is not a light either.
#
# **`soft_light` is a backlight, and a backlight is the exact shape of this
# problem.** Godot adds `backlight * (1 - N.L)` per light: a term that is zero
# on the faces the key already reaches and largest on the faces it misses
# entirely. That is a shadow floor tied to the real light directions, which is
# what "soft bounce contribution" means when it is not spelt as a fifth
# directional light. A fifth light would have raised the lit faces too, given
# the faces pointing at *it* a second key, and - because it is a light - been
# one profile mistake away from reaching the machine. This cannot: it is a
# field on nine world materials, and the machine's materials are not in the
# table.
#
# **The albedos come up, and by a measured amount.** V25's base darkened the
# kit's own values hard - `world_rock` to #0C1119, which is L* 6 - so the
# recession would survive and the machine would stay hero. At L* 6 a facet the
# key misses has nothing left to render. These lift each surface by four to
# six L*, **keeping the six-L* spacing between the depth pairs that V25.1's
# section 3 argues for**, and the machine's own body is at L* 85: the
# separation this spends is a rounding error against it, and it is measured.

#: A cool, low backlight for the rock, and one warm one for the finish.
#: Deliberately *not* the fog colour - the fog is #15293F and a backlight of
#: the same hue would read as haze creeping onto near geometry.
_SOFT_NEAR = "#0C1420"
_SOFT_COOL = "#0C1520"
_SOFT_MID = "#0A1220"
_SOFT_WARM = "#2A1D14"
_SOFT_LEAF = "#0C1A12"

PALETTE = {
    # --- the near and mid rock, in the pairs V25.1 established -------------
    # Each pair keeps its face-to-ledge step and each band keeps its distance
    # from the next. What changes is the floor they all sit on.
    "world_cliff_face": {
        "albedo": "#19202F", "roughness": 0.93,
        "soft_light": _SOFT_COOL, "vertex_tint": True,
    },
    "world_cliff_ledge": {
        "albedo": "#222C3B", "roughness": 0.92,
        "soft_light": _SOFT_COOL, "vertex_tint": True,
    },
    "world_wall_face": {
        "albedo": "#1B2739", "roughness": 0.95,
        "soft_light": _SOFT_MID, "vertex_tint": True,
    },
    "world_wall_ledge": {
        "albedo": "#24344C", "roughness": 0.94,
        "soft_light": _SOFT_MID, "vertex_tint": True,
    },
    # **The near rock turns off blue, and that is the anti-monochrome move.**
    # V25's recession is carried by *value* alone - six surfaces, one hue - so
    # a world with five depth bands in it still reads as one colour. Aerial
    # perspective is a hue effect before it is a value effect: what is close
    # is the local stone and what is far is the colour of the air between.
    # So the foreground pair sits near-neutral slate, the midground pair keeps
    # V25's blue, and the valley walls are the bluest thing that is not sky.
    # Nothing here is warm; the world stays cool. It is no longer *one* cool.
    "world_scarp": {
        "albedo": "#1D2229", "roughness": 0.92,
        "soft_light": _SOFT_NEAR, "vertex_tint": True,
    },
    "world_rock": {
        "albedo": "#191E25", "roughness": 0.92,
        "soft_light": _SOFT_NEAR, "vertex_tint": True,
    },
    "world_soil": {
        "albedo": "#262B34", "roughness": 0.92,
        "soft_light": _SOFT_NEAR, "vertex_tint": True,
    },
    # The gorge banks stay the darkest rock in the world - the water reads by
    # being a smooth plane against broken rock, and lifting the banks to match
    # the cliffs would take that contrast away. They get the floor, no lift.
    "world_damp": {"soft_light": _SOFT_MID, "vertex_tint": True},
    "world_wet": {"soft_light": _SOFT_MID},

    # --- C: the warmth, in the brief's own hierarchy -----------------------
    #
    # Warmest at the finish, then the machine-adjacent structures, then a few
    # rock faces, then nothing at all on the far mountains. Every one of these
    # is a *turn* rather than a hue: the world stays cool, and what these buy
    # is that it is no longer only one colour.
    #
    # The finish rim. V25.1 named this "warm means not blue" and picked a
    # neutral; at the distance the finish camera stands it read as another
    # grey rock. This is the one surface in the world allowed an actual warm
    # cast, it is thirty units of rock behind the payoff, and it is the single
    # strongest thing this pass does for the finish.
    # **It was not warm, and the measure caught that before the eye did.**
    # V25.1's value is #242130 and the first version of this one was #2E2833:
    # both have *more blue than red*, so "warm rock" was a cool grey with a
    # warm name. The first render's finish warm-pixel fraction came back at
    # 0.2% against V25.1's 0.6% - the pass had made the finish measurably
    # *cooler*, because everything else in the frame lifted and the rock did
    # not turn. This is the correction: red leads blue by seventeen levels,
    # which under a cool key and a warm practical is a rock that is plainly a
    # different colour from the gorge under it and is still nowhere near
    # orange.
    "world_warm_rock": {
        "albedo": "#3B3029", "roughness": 0.93,
        "soft_light": _SOFT_WARM, "vertex_tint": True,
    },
    # The ground inside the basin, warmed and lifted with it.
    "world_ember": {"albedo": "#453C39", "roughness": 0.92,
                    "soft_light": _SOFT_WARM},
    # Engineering concrete: the machine's own footings, second in the
    # hierarchy. A quarter-stop of warmth and a lifted floor, so a bench wall
    # in shadow is a wall rather than a hole.
    "world_concrete": {"albedo": "#3A3F49", "soft_light": "#221E1A"},
    "world_deck": {"albedo": "#333A48", "soft_light": _SOFT_COOL},
    "world_deck_dark": {"albedo": "#1E242E", "soft_light": _SOFT_COOL},

    # --- E: the obstacle's own stone ---------------------------------------
    #
    # A distinct rock material for the one section that had no local identity,
    # and the brief lists exactly that as a way to give it one. Slate rather
    # than navy: the same value as the cliffs and a hue turn off them, so the
    # pocket reads as a different *kind of country* without reading as a
    # different *light*.
    "world_pocket": {
        "albedo": "#1D2630", "roughness": 0.90,
        "soft_light": "#131C1E", "vertex_tint": True,
    },
    # The ground of the same place, and two separate keys from the rock - see
    # `lab_palette` and `sloped/v252_world.MARKED` for the measurement that
    # forced the split. Close to the hillside in value, off it in hue, one of
    # them a stop rougher: a change of material, not a painted patch.
    "world_pocket_floor": {"albedo": "#2C333B", "roughness": 0.93},
    "world_pocket_grit": {"albedo": "#333940", "roughness": 0.98},

    # --- H: the ground -----------------------------------------------------
    #
    # The near ground is a third of several frames and it is the one surface a
    # vertex gradient cannot reach - `_patches` and the heightfield are not
    # rock-kit meshes. So it is done with value, hue and roughness, which is
    # all the brief allows anyway: no tiling map, no high-frequency noise.
    #
    # The hillside comes up two L* and turns a few degrees off blue; the zones
    # keep their half-stop separation from it and gain a roughness spread, so
    # a zone boundary is a change of sheen as well as of hue and stops reading
    # as a painted polygon.
    "slope_earth": {"albedo": "#2F3846", "roughness": 0.95},
    "slope_rock": {"albedo": "#242B36", "roughness": 0.94},
    "slope_cliff": {"albedo": "#1F2530", "roughness": 0.94,
                    "soft_light": _SOFT_COOL},
    "slope_scree": {"albedo": "#2A323F", "roughness": 0.97},
    "slope_cap": {"albedo": "#282E3A", "roughness": 0.93},
    "slope_boulder": {"albedo": "#1E242E", "soft_light": _SOFT_COOL},
    "world_gravel": {"albedo": "#333B49", "roughness": 0.99},
    "world_bench": {"albedo": "#2F343C", "roughness": 0.90},

    # --- D: the vegetation --------------------------------------------------
    #
    # Two greens rather than two teals. V25's conifers are #0F241E and
    # #16302A, which are cyan-greens - in a cyan world that is camouflage at
    # distance and a teal triangle up close. These keep the same value and
    # move the hue toward an actual conifer, which also puts a second hue
    # family in a picture that had one.
    "conifer_deep": {"albedo": "#15281C", "soft_light": _SOFT_LEAF},
    "conifer_dark": {"albedo": "#1D3325", "soft_light": _SOFT_LEAF},
    "world_shrub": {"albedo": "#21301F", "soft_light": _SOFT_LEAF},

    # The practicals' own lenses, warmed with the lamps they belong to.
    "lit_world_amber": {"emission": "#FFC48C", "energy": 2.3},
}


# --- C: the light rig -------------------------------------------------------
#
# Three dials, no new light, and the whole change is under a tenth of a stop on
# the world's total.
#
# V25.1's section 11 is right that the warm fill is the world's only warmth and
# that cutting it was the mistake. It is now *worth* more than it was, for a
# reason that is the whole of Part A: against untempered facets a fill lands as
# a second flat value on whichever faces happen to point at it, and against
# tempered ones it lands as a gradient that turns across the form. The same
# energy buys more.
#
# `WorldBounce` comes up because V25.1's own falsification of it was measured
# *before* the material floor existed: it was being asked to do alone what a
# backlight does better, at a bearing where nothing faced it. It now finishes
# the job rather than being the job. `WorldKey` pays for both, so the world's
# lit faces are where they were and only the unlit ones moved.
#
# **And `WorldRim` comes down, which is the one dial that moves in the
# direction nobody expected.** V25.1 raised it from 0.55 to 0.66 with a good
# argument - "a rake has edges to find now" - and against tempered normals that
# argument inverts. A rake on a hard facet catches one edge; a rake on a
# tempered one catches a whole turning surface, and `WorldRim` is #63BEE8. The
# first V25.2 render put a cyan sheen across every upward-facing plane in the
# finish rim, which is both the "monochromatic" complaint and the
# "prototype-like" one arriving together. 0.50 is under V25's own 0.55 and the
# edges still read, because they are now the only thing it is catching.
LIGHTS = {
    "WorldKey": {"energy": 1.52},
    "WorldWarm": {"energy": 1.20},
    "WorldBounce": {"energy": 0.70},
    "WorldRim": {"energy": 0.50},
}


# --- B: the hero rocks ------------------------------------------------------
#
# The brief's rule is silhouette first, surface second, and its test is that a
# hero rock should still look intentional as a black shape. So this section
# spends `overhang`, `shoulder` and `jag` and nothing else - three options that
# all move the *outline* - and it spends them only on the formations the race
# cameras stand closest to.
#
# It also spends them **unevenly**, on purpose. Every form getting one overhang
# and one shoulder is a new repeated shape, which is the failure the kit was
# built to escape; a hero gets both, a supporting mass gets one.


def look(temper: float, shade: float, **extra) -> dict:
    """What the shading options are worth for one band, and why they differ.

    `temper` is highest where the mosaic is worst and the form is furthest
    away, and lowest on the needles - a spire is a silhouette, and softening it
    is spending the one thing it has.

    `crease` is 42 degrees everywhere, and that single number is doing more
    work than it looks. The plan step on an 11-facet form is 33 degrees and on
    a 7-facet needle is 51: so the crowded facets of a wide mass blend and the
    few facets of a thin one do not, from one threshold, with no per-kind
    table to keep in step.
    """
    spec = {"temper": temper, "crease": 42.0, "shade": shade,
            "shade_crown": 0.32, "shade_foot": 0.30, "shade_bearing": 58.0}
    spec.update(extra)
    return spec


#: The near midground ridge band: nine `cliff` masses at radius 100. **This is
#: the band the whole pass exists for** - the one V25.1 measured at 42.2% dark
#: and the one a viewer calls a folded-paper mosaic. It gets the most temper a
#: near form can take, the full gradient, a jagged crown and a shoulder.
RIDGE_NEAR = look(0.62, 1.0, jag=0.11, shoulder=1, shade_warm=0.07,
                  shade_cool=0.05)
#: The far midground: seventeen `mountain` masses at 188. More temper, less
#: gradient - at that distance an internal value change competes with the
#: aerial perspective that is doing the recession.
RIDGE_FAR = look(0.66, 0.7, jag=0.06, shade_cool=0.06)
#: The valley walls at 300. Almost no warmth, per the brief's hierarchy, and
#: the most temper of anything: at 300 units a facet is a large flat region of
#: one value and there is no silhouette argument left to protect.
WALLS = look(0.70, 0.5, shade_cool=0.05)
#: The cut ledges on the near ground. Read for their horizontals, so the crease
#: has to keep those hard: temper is moderate and `jag` is small.
SCARPS = look(0.46, 0.9, jag=0.05, shade_warm=0.05)
#: The spires. Lowest temper in the world - see `look`.
SPIRES = look(0.30, 0.8, shade_cool=0.04)
#: The boulders, at 7 to 32 units: the closest rock to any lens.
BOULDERS = look(0.44, 0.95, jag=0.16, shoulder=1, shade_warm=0.06,
                shade_cool=0.05)
#: The ravine banks, down in the dark.
BANKS = look(0.52, 0.6, shade_cool=0.08)


# --- the world deltas -------------------------------------------------------


def _shape(base: dict, extra: dict) -> dict:
    """One site's `shape`, with this pass's options merged over V25.1's."""
    out = dict(base.get("shape", {}))
    out.update(extra)
    return out


#: Part I, applied. Nothing is added anywhere in this file; three counts come
#: down, and each comes down where the object was contributing least.
#:
#:   boulders 46 -> 42   the smallest are under a unit across at thirty units
#:   spires   26 -> 22   V25.1 already called this the feature that buys the
#:                       least silhouette per node, and cut it once
#:   scarps   12 -> 11   the site at -48,-72 is behind the start backboard in
#:                       every frame it appears in
_DROPPED_SCARP = [-48.0, -72.0]
_SCARP_SITES = [one for one in v251.SCARPS["sites"]
                if list(one[:2]) != _DROPPED_SCARP]
assert len(_SCARP_SITES) == len(v251.SCARPS["sites"]) - 1

#: The near ground. Two changes, both of them Part H and neither of them a
#: texture: the zone shades like the terrain it lies on rather than as its own
#: flat-shaded mosaic, and its boundary is a curve at 24 facets rather than a
#: 13-sided polygon. `rough` comes up a little with the facet count so the
#: coastline still has bays in it at the new resolution.
#:
#: **And two of the eleven zones become the obstacle's own ground.** Segmenting
#: the obstacle frame by band settles what that camera actually sees: the top
#: eighth is foreground rock, and everything from v = 0.25 down - five eighths
#: of the picture, up to 100% of some rows - is *terrain*. Ridges are 1.8% of
#: it and `world_pocket` did not appear in it at all on the first render.
#:
#: So the pocket has to be built out of the ground, because the ground is what
#: is there. The zone at (-10, -4) is centred within a unit of the obstacle
#: node itself and the one at (-9, 10) sits just up-course of it; repainting
#: those two in the slate pair, and widening the first, makes the floor the
#: obstacle machine stands on a different stone from the rest of the valley
#: across most of that frame. No zone is added and none is moved.
PATCHES = {
    "smooth": True, "facets": 24, "rings": 8, "rough": 0.34,
    "sites": [
        list(one) if list(one[:2]) not in ([-10.0, -4.0], [-9.0, 10.0])
        else (one[:2] + [19.0, "world_pocket_floor"] if list(one[:2]) == [-10.0, -4.0]
              else one[:2] + [one[2], "world_pocket_grit"])
        for one in v251.PATCHES["sites"]
    ],
}

WORLD = {
    "patches": PATCHES,
    "walls": {"shape": _shape(v251.WALLS, WALLS)},
    "ridges": {
        "bands": [
            dict(v251.RIDGES["bands"][0],
                 shape=_shape(v251.RIDGES["bands"][0], RIDGE_NEAR)),
            dict(v251.RIDGES["bands"][1],
                 shape=_shape(v251.RIDGES["bands"][1], RIDGE_FAR)),
        ],
    },
    "scarps": {"sites": _SCARP_SITES, "shape": _shape(v251.SCARPS, SCARPS)},
    "spires": {"count": 22, "shape": _shape(v251.SPIRES, SPIRES)},
    "boulders": {"count": 42, "shape": _shape(v251.BOULDERS, BOULDERS)},
    "ravine": {"shape": _shape(v251.RAVINE, BANKS)},
}


# --- D: the vegetation ------------------------------------------------------
#
# No more plants, and no more triangles per plant to speak of. Three form
# options and one composition change.
#
# `bough` at 0.34 is the important one: it takes the apex of every crown tier
# a third of a radius off the axis, which is the difference between a stack of
# cones and a tree with boughs. `ragged` breaks the lower rim of each tier so
# the outline has tips on it. `aspect` puts a third of a stop of width spread
# on the kind itself, so two conifers in one stand are two trees.
#
# And the composition takes a `snag`. One dead stem in a stand of nine is the
# brief's "at least three visibly distinct silhouettes" bought for about thirty
# triangles, and it is the only plant in the kit whose outline is a vertical
# line rather than a triangle.
TREES = {
    "shape": {"bough": 0.34, "ragged": 0.24, "aspect": 0.34},
    "roles": ["hero", "conifer", "spruce", "snag", "conifer", "shrub",
              "spruce", "tuft", "conifer"],
}


# --- E: the obstacle pocket -------------------------------------------------
#
# The brief is explicit that the obstacle's camera does not see mid-distance
# well and that a distant landmark is therefore the wrong answer. What it can
# see is the uphill wall, which fills the whole left of the frame at 10.2 s -
# so the identity has to be built *there*, out of the mass that is already
# there, and out of nothing that is new.
#
# Three moves on one existing landmark, and one on an existing lamp:
#
#   1. **It leans over the section.** An `overhang` high on the mass and a
#      `shoulder` above it turn a broad stepped mesa into a wall with
#      something hanging off it - the "partial overhang" and "close canyon
#      wall" the brief lists, at zero node cost.
#   2. **It is its own stone.** `world_pocket` is a slate against the valley's
#      navy: same value, different hue family. A viewer reads a change of
#      country before they read a change of rock.
#   3. **It comes in and up.** From 55 units out and 44 tall to 48 and 52,
#      which at the obstacle camera's distance is the difference between a
#      mass in the background and a wall the machine stands under. It moves
#      along the wall rather than toward the racing line, and the builder's
#      clearance and lens keep-outs still adjudicate it.
#
# And the warm/cool pocket: the obstacle's amber practical goes from 0.9 to
# 1.35 and moves ten units along, so the near face of the wall carries a warm
# edge against a cool world. That is the brief's "warm/cool lighting pocket",
# and it is a retune of a lamp that already exists.
#: The five formations the race cameras stand closest to, as **deltas**.
#: The profile merge is deep and a `shape` is a dictionary, so a site here
#: names only what it changes and inherits every number V25.1 chose. That is
#: also the guard: a hero rock this pass forgets is a hero rock that still
#: builds exactly as it did.
OBSTACLE = {
    # The three moves above, as data - and the first of them is smaller than
    # it was first written, because the builder said so.
    #
    # **The keep-out adjudicated this and it was right to, twice.** The first
    # build asked for 48 units and `environment_world` rejected it; the second
    # asked for 54 through `near()` and was rejected at 8.4 units from the
    # camera path, which is not where 54 is. `near()` converts an *absolute
    # plan position* into a terrain-relative offset, and a site that names a
    # `node` wants a plain node-relative offset - so it was being added to the
    # anchor twice and landing eleven units from where it was written. The
    # measured rejection reason is what found that in one render, and it is in
    # `environment_world._why` because of it.
    #
    # 54 is one unit in from V25.1's 55, and clears the lens at 17.8 against
    # the 16 it needs. The looming is bought by the height and the overhang
    # instead: what makes a wall lean over a shot is its top edge against the
    # sky, not its footprint.
    "offset": [54.0, -2.0],
    "height": 54.0,
    "base": 21.0,
    "kit": "cliff",
    "facets": 13,
    "material": "world_pocket",
    "shape": look(0.50, 1.0, cap=0.52, lobe=0.54, step=0.115,
                  overhang=1, overhang_step=0.15, shoulder=1, jag=0.13,
                  batter=0.50, shade_warm=0.12, shade_cool=0.06),
}


# --- F: the finish ----------------------------------------------------------
#
# The brief's own words are that the machine is strong and the environment is
# weak, and the frame agrees: at 21.4 s the FINISH board and the gold chute are
# excellent and everything behind them is unrelated dark blue polygons.
#
# What a destination needs is not more objects. It is that the objects already
# there stop being a backdrop and start being a **room** - and V25.1 already
# built the room, five masses on an arc that opens toward the camera, over four
# more down in the gorge. Four changes make it read as one:
#
#   1. **The rim becomes one wall.** `temper` at 0.58 across the arc, so the
#      five masses shade as a continuous surface instead of as five silhouette
#      cards, and each carries the vertical gradient - dark at the gorge,
#      lifting toward its crown.
#   2. **The crown breaks.** `jag` 0.17 and one shoulder, so the rim has a
#      skyline instead of a fence line, and one overhang so it has a corner.
#   3. **It is warm, and it is the only warm rock in the world.**
#      `world_warm_rock` carries a real cast now, and the vertex gradient turns
#      0.16 of warmth onto the faces the fill rakes - so the upper basin
#      separates from the cold lower one by hue as well as by value. That is
#      the two-tier readability the brief asks for, bought with light rather
#      than with geometry.
#   4. **The practicals mean it.** Three lamps already stand at the finish and
#      nothing else in the world has more than one. They go warmer and up about
#      a third, and the high one comes up and out to rake the rim rather than
#      the deck.
#
# The camera is not touched, the arc's bearings are not touched, the crown
# heights are not touched, and no track, structure or stadium is added.
#: **And the finding the finish pass is built on: V25.1's basin is outside the
#: lens.** Projecting the five arc masses through the finish camera's own
#: solved transform puts their crowns at screen u = 1.64, 1.04, 0.29, -0.41 and
#: -0.80, and the one that is horizontally in frame has its crown at v = -0.34
#: - a third of a frame height *above* the top edge. So four of the five masses
#: are off the sides and the fifth is a wall whose top the camera never sees.
#:
#: That is not a shading problem and no amount of temper, warmth or jag was
#: ever going to fix it. It is also not a mistake anybody could have caught
#: from a plan view: the finish camera is 36 degrees vertical on a 9:16 frame,
#: which is **20.7 degrees horizontal**, and an arc of radius 30 at 40 to 65
#: units subtends about ninety.
#:
#: So the arc is re-solved against the lens rather than against the map: 60 to
#: 120 degrees at radius 22, which puts the five masses at u = 0.93, 0.71,
#: 0.46, 0.22 and 0.04 - spread across the whole width - and `crown` comes down
#: from 14 to 2 so the middle of the rim tops out just inside the frame instead
#: of a third of a frame above it. `base` comes down with the radius so the
#: masses still overlap into one continuous rim rather than five towers.
#:
#: Nothing about the camera moved. This is the brief's Part G done the way it
#: asks for it: compose the world around the camera we already have.
FINISH = {
    "from": 60.0,
    "to": 120.0,
    "radius": 22.0,
    "crown": 2.0,
    "fall_y": 16.0,
    "base": 12.0,
    # Tapered and broken rather than stacked: the first solved arc came back
    # as a row of cubes behind the board, because `cliff` and `block` at the
    # kit's own caps are flat-topped by design and five flat tops in a line is
    # a wall of boxes. A hard taper, a strong batter and a small cap make them
    # masses that narrow as they rise; `jag` at 0.26 is what stops the five
    # narrow tops being a row of the same narrow top.
    "shape": look(0.58, 1.0, jag=0.26, shoulder=1, overhang=1,
                  overhang_step=0.12, shade_warm=0.40, shade_cool=0.07,
                  shade_crown=0.36, taper=0.46, batter=0.56, cap=0.22,
                  lobe=0.46),
}

#: The lower rim, down in the gorge. It gets the shading response and **no
#: warmth at all** - the brief asks for a darker lower ravine and the two-tier
#: read depends on the tiers being different. `shade_foot` is raised instead,
#: so the bottom of the gorge falls away rather than filling in.
#: The lower rim, down in the gorge, re-solved on the same bearings so the two
#: tiers are one composition rather than two arcs that happen to share a
#: centre. It gets the shading response and **no warmth at all** - the brief
#: asks for a darker lower ravine, and a two-tier read depends on the tiers
#: being different. `shade_foot` is raised instead, so the bottom of the gorge
#: falls away rather than filling in.
FINISH_FLOOR = {
    "from": 64.0,
    "to": 124.0,
    "radius": 15.0,
    "crown": -22.0,
    "fall_y": 14.0,
    "base": 9.0,
    "shape": look(0.56, 0.8, shade_cool=0.09, shade_foot=0.40,
                  shade_crown=0.24),
}

#: The other three formations. Each gets the shading response and one
#: silhouette event, and no two get the same one - a rule that only matters
#: because breaking it is how a kit turns back into a preset.
GORGE_TEETH = {"shape": look(0.34, 0.9, jag=0.09, shade_cool=0.07)}
SPLIT = {"shape": look(0.48, 1.0, jag=0.14, shoulder=1, shade_warm=0.06,
                       shade_cool=0.06)}
MERGE = {"shape": look(0.54, 0.9, jag=0.08, overhang=1, shade_cool=0.06)}

LANDMARKS = {
    "sites": {
        "east_wall": OBSTACLE,
        "gorge_teeth": GORGE_TEETH,
        "split": SPLIT,
        "merge_narrows": MERGE,
        "finish": FINISH,
        "finish_floor": FINISH_FLOOR,
    },
}

#: Six lamps, exactly as many as V25.1 has, in the same six places bar two
#: offsets. Warmth is bought here by *colour and aim*, not by count - the
#: brief's own warning is that a dark world takes any amount of light before it
#: looks full, and the frame where it looks full is the frame the machine
#: stopped being the brightest thing in it.
LAMPS = {
    "sites": [
        # The obstacle's warm/cool pocket: brighter, and moved along toward
        # the new wall's near face.
        # Above the pocket floor and on the camera's own side of it, rather
        # than nine units *under* the track where V25.1 put it: what this has
        # to light is the slate ground the obstacle machine stands on, and a
        # lamp below the deck lights the underside of the deck.
        ["obstacle", -13.0, 4.0, -8.0, "#FFB877", 1.60, 30.0, 1.6],
        # The fork stays cool. It is the one place in the film where the orange
        # route has to read as orange, and a warm practical there would be
        # competing with it - the brief says so twice.
        ["split", 26.0, -16.0, 8.0, "#7FD8FF", 0.7, 30.0, 1.7],
        ["merge", -20.0, -7.0, 4.0, "#8FD0F0", 0.6, 24.0, 1.7],
        # The finish. Warmest place in the world, and these are why.
        #
        # **The third one exists because of a mechanism, not a taste.** A warm
        # albedo cannot make a warm picture under a cool light, and the light
        # reaching the rim's camera-facing side is `WorldBounce` at #35618F -
        # the warm fill rakes from bearing +58 and the finish camera stands to
        # the south-west, so it sees precisely the faces the warm light misses.
        # Turning the rock warmer moved its red-minus-blue by 37 levels and its
        # crossover count by nothing, which is the whole story in two numbers.
        #
        # An omni between the deck and the rim is the fix and it is the brief's
        # own listed lever - "finish basin practicals". V25.1's third finish
        # lamp sat 44 units up-gorge at range 38, which is past the far horn
        # and lights nothing in shot; this one stands 14 out and 12 along at
        # range 40, which puts every arc mass 11 to 18 units from it. World
        # cull mask, like every lamp here: it cannot reach the machine.
        ["finish", 22.0, -4.0, 18.0, "#FFC98A", 1.45, 30.0, 1.5],
        ["finish", -14.0, -6.0, 22.0, "#FFB469", 1.05, 26.0, 1.6],
        ["finish", 14.0, -3.0, 12.0, "#FFB878", 4.20, 40.0, 1.3],
    ],
}


PROFILE = {
    "id": "aurora_valley_v252",
    "title": "Aurora Valley V25.2 - final world lookdev",
    "family": "valley",
    "summary": (
        "V25.1's world at V25.1's density, with the midground shading response "
        "rebuilt: crease-limited normal softening, a baked albedo gradient and "
        "a material shadow floor on every rock, restrained warmth in the "
        "brief's hierarchy, broken silhouettes on the five hero formations, "
        "leaning and ragged vegetation, a slate pocket at the obstacle and a "
        "warm two-tier basin at the finish"
    ),
    "extends": "aurora_valley_v251",
    "lights": LIGHTS,
    "palette": PALETTE,
    "world": dict(WORLD, trees=TREES, landmarks=LANDMARKS, lamps=LAMPS),
}


# --- the marker -------------------------------------------------------------


def _marker() -> dict:
    """V25.2 painted flat by depth band, for the segmentation.

    Written from `sloped.v252_world.MARKED`, for the reason V25.1 gives: a
    surface added to the world and not to that table shows up in the sheet as
    a hole rather than as somebody else's band.
    """
    from sloped import v252_world

    palette: dict = {}
    for band, keys in v252_world.MARKED.items():
        hue = "#%02X%02X%02X" % v252_world.layer_hue(band)
        for key in keys:
            palette[key] = {"albedo": hue, "unshaded": True, "no_fog": True}
    return {
        "id": "_marker_v252",
        "title": "Marker over aurora_valley_v252 (diagnostic)",
        "family": "diagnostic",
        "summary": (
            "aurora_valley_v252 with every world surface painted the flat hue "
            "of its depth band, so a render of it can be segmented by depth"
        ),
        "extends": "aurora_valley_v252",
        "palette": palette,
    }


def profiles() -> list[dict]:
    return [PROFILE, _marker()]


def write(check: bool = False) -> list[str]:
    stale: list[str] = []
    for profile in profiles():
        path = os.path.join(PROFILE_DIR, f"{profile['id']}.json")
        text = json.dumps(profile, indent=2) + "\n"
        old = ""
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                old = handle.read()
        if old == text:
            continue
        stale.append(path)
        if not check:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
    index_path = os.path.join(PROFILE_DIR, "index.json")
    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)
    wanted = [one["id"] for one in profiles()]
    missing = [one for one in wanted if one not in index["profiles"]]
    if missing:
        stale.append(index_path)
        if not check:
            index["profiles"].extend(missing)
            with open(index_path, "w", encoding="utf-8",
                      newline="\n") as handle:
                handle.write(json.dumps(index, indent=2) + "\n")
    return stale


if __name__ == "__main__":
    checking = "--check" in sys.argv
    changes = write(check=checking)
    for path in changes:
        print("stale" if checking else "wrote",
              os.path.relpath(path, PROJECT_ROOT))
    if not changes:
        print("profiles are already up to date")
    sys.exit(1 if (checking and changes) else 0)

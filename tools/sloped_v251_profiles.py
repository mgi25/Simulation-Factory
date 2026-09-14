"""V25.1: the world-art profile, written from one source.

    python tools/sloped_v251_profiles.py          # write the JSON
    python tools/sloped_v251_profiles.py --check   # fail if it is stale

One profile and one marker:

    aurora_valley_v251     the art pass
    _marker_v251           the same, painted flat by depth band

**Not a variant of B.** `aurora_valley_v251` extends `aurora_valley_v25` - the
shared V25 base that holds the camera keep-out, the recession palette and the
fog - and restates the whole `world` section. Extending `aurora_valley_v25b`
would have been shorter and would have made every number B chose invisible
unless V25.1 happened to override it; the brief's density target is B's layout,
and a *target* is something to state, not something to inherit by accident.

So B is the control and V25.1 is a sibling, and the diff between the two files
is the whole of the art change.

**Nothing here is landform, physics or camera.** A profile is data; the world
builder makes meshes on the world light layer and no collider. See
`docs/sloped_race_v251_world.md`.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from tools import sloped_v25_profiles as v25  # noqa: E402

PROFILE_DIR = v25.PROFILE_DIR

#: The layout the course is built on, and the two constants every site below
#: is expressed against. Read from `sloped.layout` rather than retyped, so a
#: profile cannot drift from the course it dresses.
from sloped import layout as _layout  # noqa: E402

CENTRE = (1.0, 6.0)
NODES = {name: (at[0], at[2]) for name, at in _layout.NODES.items()}


def at(x: float, z: float) -> list[float]:
    """An absolute plan position as the terrain-relative offset a spec wants."""
    return [round(x - CENTRE[0], 2), round(z - CENTRE[1], 2)]


def near(node: str, dx: float, dz: float) -> list[float]:
    """The same, relative to a named race location."""
    return at(NODES[node][0] + dx, NODES[node][1] + dz)


# --- the light rig ----------------------------------------------------------
#
# Three dials and one new light. Parts C and D of the brief.

LIGHTS = {
    # **The warm world fill, restored and raised - not added.**
    #
    # The first version of this profile set `WorldWarm` to 0.34 at bearing
    # -104, on the stated reasoning that V25's own weakness 5 is "there is no
    # warmth in the world at all" and that a light costs no albedo.
    #
    # Half of that was wrong, and it is worth recording exactly how. **V23's
    # `aurora_valley` already carries a `WorldWarm`** - #FFAE62 at energy 0.9,
    # raking from bearing +52, opposite the cool `WorldKey` at -78. So the
    # profile was not adding a warm fill; it was **cutting the existing one by
    # 62% and pointing it round onto the key's own side**, where it filled
    # nothing.
    #
    # The render said so before the reading of the profile did: a
    # full-resolution crop of the split frame's background came back with a
    # near-black left half, on a pass whose whole point is that faceted rock
    # should read as planes. A flat facet has no shading gradient by
    # construction, so the side of a form the key misses is one flat value -
    # and if the fill does not reach it, that value is black. Smooth rock
    # hides a missing fill; faceted rock cannot.
    #
    # So: V23's own bearing and colour, and 17% more of it, which is the
    # smallest lift that gives every facet on a shadowed face a value to be.
    "WorldWarm": {
        "cull_mask": 2,
        "colour": "#FFAE62",
        "energy": 1.05,
        "specular": 0.0,
        "rotation": [-11.0, 58.0, 0.0],
        "shadow": {"enabled": False},
    },
    # **The one genuinely new light, and it exists because of a measurement.**
    #
    # The world rig V23 built and V25 kept has four directional lights, at
    # bearings -78 (`WorldKey`), +26 (`WorldFill`), +58 (`WorldWarm`) and +96
    # (`WorldRim`). That is a 174-degree arc, and **everything facing the
    # other 186 degrees is lit by ambient alone.**
    #
    # `smooth_mass` hides that completely: its normals vary continuously, so a
    # large face is never all on the wrong side of every light, and the eye
    # reads the average. A flat facet has one normal, and a facet pointing
    # south is *entirely* in the gap. Segmented off the marker render, the
    # ridge band in the left half of the split frame measures grey 7.9 against
    # V25 B's 27.1 in the same pixels - a nineteen-point drop in one region of
    # a frame whose overall mean moved by one point.
    #
    # So: a low cool rake from +208, which is the middle of the hole. Cool
    # rather than warm on purpose - the warm fill is one direction and keeping
    # it that way is what makes the warm/cool break read as a break rather
    # than as a tint.
    "WorldBounce": {
        "cull_mask": 2,
        "colour": "#35618F",
        "energy": 0.55,
        "specular": 0.0,
        "rotation": [-6.0, 208.0, 0.0],
        "shadow": {"enabled": False},
    },
    # **And the cool rim comes up a little.** V25 set `WorldRim` at 0.55
    # against `smooth_mass`, where a rim light has little to catch - a
    # continuous shading field has no edges for a rake to find. The kit has
    # edges everywhere, so the same light now does visible work and can afford
    # to do slightly more of it.
    "WorldRim": {"energy": 0.66},
    # A shade off the key, to pay for the warm fill. The sum of the world's
    # light is deliberately not allowed to rise: the machine's headroom is the
    # one number this pass may not spend.
    "WorldKey": {"energy": 1.58},
}


# --- A: the landform, rebuilt from the kit ----------------------------------
#
# Same bands, same radii, same bearings as B. What changes is `kit`, which
# routes every mass through `world_rock.form` instead of `hero_world.
# smooth_mass`, and `crest`, which goes to zero because the kit's own ridge
# crowns and buttresses do what the crest teeth were bolted on to fake.

WALLS = dict(
    v25.WALLS,
    kit="mountain",
    crest=0,
    # The kit's `mountain` is already a wide, low, ridge-crowned mass, so the
    # ring's own taper and facet numbers stop being used - they are left in
    # place because a profile that deleted them would not fall back to V25's
    # shape if `kit` were ever removed.
    shape={"ridge": 0.34, "buttress": 2, "lobe": 0.42},
)

# **The distant range is not a scaled-up foreground rock**, which is the
# brief's Part M in one line. Two things separate them and neither is size:
# the walls are `mountain` (ridge crown, wide plan, strong batter) and the
# ridges are `cliff` and `wall` (flat crown, ledges, vertical faces). At three
# hundred units the ridge crown is what says "range" and the flat crown is
# what says "mesa", and having both is what makes the stack read as depth
# rather than as one thing at three sizes.
#
# **And the ridge faces are sloped, not vertical, for a measured reason.** The
# first build gave band 0 the `wall` kit (taper 0.28) and band 1 `cliff`
# (0.46), and segmented off the marker render the ridge band came back at
# **42% of its pixels under grey 12 against V25 B's 23%**, while every other
# band got *lighter* - the foreground's median went from 18 to 43 and the
# valley walls' from 29 to 48.
#
# A near-vertical flat facet is a binary: its normal is horizontal, so it
# either faces a light and takes the full cosine or faces away and takes
# nothing. A sloped facet takes some light from every direction above it.
# `smooth_mass` never showed this because its normals sweep continuously
# through both cases across any large face.
#
# So the ridges get the kit's two most battered forms. It also happens to be
# the right art: the progression cliff -> mountain -> mountain-with-a-bigger-
# ridge across 100, 190 and 300 units is the brief's Part M, and a distant
# mass that is a scaled-up foreground rock is exactly what it warns about.
RIDGES = dict(
    v25.RIDGES,
    crest=0,
    bands=[
        dict(v25.RIDGES["bands"][0], kit="cliff",
             shape={"ledges": 2, "lobe": 0.34, "buttress": 2,
                    "taper": 0.46, "batter": 0.58}),
        dict(v25.RIDGES["bands"][1], kit="mountain",
             shape={"ledges": 2, "buttress": 2, "lobe": 0.38,
                    "ridge": 0.2, "taper": 0.54, "batter": 0.6}),
    ],
)

# **Twelve sites, three steps each, instead of twelve stacks of five slabs.**
# Same authored places - these were sited against the layout and re-siting
# them would be re-answering a question V25 already answered - and a different
# thing at each of them. See `environment_world._scarps` for what was wrong
# with the slab stack; the short version is that sixty rounded boxes on a
# smooth hillside are sixty boxes.
SCARPS = dict(
    v25.SCARPS,
    kit="ledge",
    steps=3,
    thickness=3.4,
    shape={"ledges": 1, "flats": 2, "lobe": 0.5, "buttress": 1},
)

# 26 rather than 38, and each one a `needle` with a buttress at its foot. Part
# Q: a scene with forty good rocks beats one with a hundred and fifty crude
# ones, and the spires are the feature where V25 bought the most count for the
# least silhouette.
SPIRES = dict(
    v25.SPIRES,
    count=26,
    kit="needle",
    height=8.0,
    height_spread=11.0,
    base=2.4,
    shape={"buttress": 1, "lobe": 0.3},
)

RAVINE = dict(
    v25.RAVINE_A,
    banks=7,
    bank_material="world_damp",
    bank_offset=38.0,
    bank_span=120.0,
    bank_height=27.0,
    bank_base=15.0,
    kit="wall",
    shape={"ledges": 2, "lobe": 0.3, "buttress": 1},
    # **The water stays, and it is a measured decision rather than a default.**
    # See §13 of the doc: the marker render puts it on screen in three of the
    # thirteen moments, and what makes it read is not reflection but the
    # contrast between one smooth plane and the broken rock around it. The
    # banks are what carry the gorge; the water is what stops it being a hole.
    water=True,
)


# --- B: the foreground ------------------------------------------------------

# 46 rather than 72, alternating two kinds. A boulder field built from one
# preset is the repetition the brief bans however many of them there are.
BOULDERS = dict(
    v25.BOULDERS,
    count=46,
    kits=["boulder", "slab", "boulder", "block"],
    scale=2.8,
    scale_spread=4.4,
    shape={"lobe": 0.42},
)

# **A bench, not a pad and four blocks.** Same sites, same spacing, same drop
# window - the siting rule was correct and is V25's - and one continuous
# retaining wall instead of an arc of separate bodies, in a concrete that is
# lighter than the hillside rather than darker than it.
# **A few convincing contact points, not a row of them.** V25 built fifteen at
# 15-unit intervals; the first V25.1 render built the same fifteen out of a
# lighter concrete and they came out as sixty pale boxes strewn across the near
# ground - a worse version of the failure they were meant to fix.
#
# The brief's Part G says exactly what to do about that, so: a third off the
# count, a third off the footprint, and a concrete four L* above the hillside
# instead of fourteen. Eleven benches instead of fifteen, each five meshes
# instead of six - 55 bodies along the racing line against V25's 90.
#
# The interval went to 24 first and gave **four**, which the instrument said
# were visible but which is too few to read as how this machine stands on this
# hill. 20 units is the setting where every one of the thirteen frames has a
# bench in it and no frame has a row of them.
ANCHORS = dict(
    v25.ANCHORS,
    form="bench",
    every=20.0,
    min_drop=2.8,
    max_drop=17.0,
    limit=12,
    pad=3.6,
    wall=1.35,
    deck="world_deck",
    kerb="world_concrete",
    stone="world_bench",
)

# 26 clusters rather than 40, and a cluster is composed rather than scattered:
# one hero, then conifers, spruces, a shrub and a tuft out toward its edge.
# About 130 plants against V25's 188, and five silhouettes instead of one.
TREES = dict(
    v25.TREES,
    kit=True,
    clusters=26,
    per_cluster=4,
    cluster_spread=3,
    spread=4.6,
    height=3.0,
    height_spread=2.6,
    # Vegetation follows the ground that would hold it: a steeper minimum
    # normal than V25's, so a cluster lands on a shelf or a bench rather than
    # on a face. This is the brief's placement note - "following ledges /
    # protected areas" - expressed as the one property of the terrain the
    # builder can actually read.
    min_normal=0.80,
    clearance=7.5,
    reach=40.0,
)


# --- C: the named places ----------------------------------------------------
#
# Five forms, each with **one dominant visual idea**, and every one of them
# placed against a frame rather than against the layout.
#
# ## The finding this section is built on
#
# V25 sited its landmarks "from the layout's own `nodes` table, so a landmark
# is at the place it is named for by construction". That is true and it is not
# sufficient, because **the camera named for a place is not looking at that
# place** - it is tracking the pack, which by the time a cut is named for a
# node has usually gone past it, and it is looking *down-course* at whatever is
# beyond.
#
# Projected into the thirteen comparison frames by `tools/
# sloped_v251_sites.py`, three of V25's five landmarks are in **no frame at
# all** - not their feet, not their middles, not their crests. The start butte
# and the obstacle spires stand on the west uphill wall, which no camera on
# this course ever sees; V25's own verdict that they "are correct and they are
# not distinctive" was generous to them.
#
# So every form here is sited where the instrument says it lands, and the
# comment on each says which frames see it. The keys are what the form *is*;
# `node` is only the origin the offset is measured from.

LANDMARKS = {
    "clearance": 12.0,
    "keepout": 16.0,
    "sites": {
        # **The east wall: the most valuable site on the course.** A mesa
        # across the gorge at (46, 2), which the instrument puts inside six of
        # the thirteen frames - the start, the mixer, the descent, the fork
        # approach, the split and the preview's return - and near an edge in
        # every one of them, between u = 0.62 and u = 0.85. That is exactly
        # what a framing element should be: present in half the film and in
        # the way of none of it.
        #
        # A broad flat crown, because the whole start sequence is verticals
        # (the mast, the backboard, the rotor) and one long horizontal high in
        # the frame is what settles them.
        "east_wall": {
            "node": "obstacle", "kind": "butte", "offset": [55.0, -1.2],
            "height": 44.0, "base": 22.0, "sink": 5.0, "seed": 1301,
            "kit": "ledge", "material": "world_cliff_face",
            "shape": {"cap": 0.78, "ledges": 2, "buttress": 2, "lobe": 0.52},
        },
        # **The gorge teeth**, where the obstacle spires used to be and
        # nowhere near where they were. Two needles at a strong height ratio
        # on the gorge's east lip, a third of the way out of centre in the
        # two frames that see them: the descent (u -0.35) and the mixer
        # (-0.35), both at about a hundred units.
        #
        # This is the brief's "distinctive paired rock needles" - it is not at
        # the obstacle, because the obstacle's camera is a 25-unit machine
        # shot whose entire visible world is the finish bowl ninety units
        # down-course. That is stated in the doc rather than worked around.
        "gorge_teeth": {
            "node": "mix", "kind": "pair", "offset": [53.6, 8.4],
            "bearing": 24.0, "gap": 15.0, "height": 27.0, "base": 6.0,
            "ratio": 0.54, "width_ratio": 0.6, "sink": 3.0, "seed": 1409,
            "lean": 0.12, "kits": ["needle", "needle"],
            "material": "world_scarp",
            "shape": {"buttress": 1, "lobe": 0.32},
        },
        # **The fork gate, made geological.** The one V25 landmark that
        # worked, and the instrument agrees - five frames see it. What changes
        # is that the two posts are now different *kinds* rather than one kind
        # at two heights: a vertical needle on one side and a broad stepped
        # mesa on the other. Two kinds of country either side of the choice,
        # so the landscape says "two ways" before the cyan and orange track
        # lighting does.
        "split": {
            "kind": "gate", "offset": [3.0, 10.0], "bearing": 88.0,
            "gap": 78.0, "height": 28.0, "base": 11.0, "ratio": 0.56,
            "width_ratio": 1.55, "sink": 3.5, "seed": 1511,
            "kits": ["needle", "ledge"], "material": "world_cliff_face",
            "shape": {"buttress": 2, "lobe": 0.4},
        },
        # **The narrows.** Two walls leaning in where the routes rejoin, at
        # (-16, 50) - a hundred units from the merge camera and three quarters
        # of the way to the right edge, which is the only placement in the
        # merge frame that is neither behind the machine nor out of shot.
        #
        # Moved twice. The first placement was rejected by the builder for
        # standing 11.3 units from the final cut's camera path against a
        # 16-unit keep-out. The second cleared every keep-out and then turned
        # up in the *finish approach* as a black wedge down the left edge,
        # partly over the checkered deck - a mass the camera never goes near
        # but looks straight past. A keep-out is a rule about where a camera
        # *goes*; nothing in a profile can express where one *looks*, which is
        # why the instrument exists.
        # Separated **along the line of sight** rather than across it, which
        # is what makes a narrows a narrows: a pair placed across the merge
        # camera's view has one post at u = 0.7 and the other off the right
        # edge, because that frame only has about thirty degrees of world in
        # it before the machine takes over. Nine units in front and nine
        # behind puts both at u = 0.67 and u = 0.98 - one wall, then another
        # wall past it, which reads as a gap to go through.
        "merge_narrows": {
            "node": "merge", "kind": "pair", "offset": [-17.0, 17.9],
            "bearing": 0.0, "gap": 18.0, "height": 28.0, "base": 9.0,
            "ratio": 0.78, "width_ratio": 0.88, "sink": 3.0, "seed": 1607,
            "lean": 0.17, "kits": ["wall", "wall"],
            "material": "world_cliff_face",
            "shape": {"ledges": 2, "buttress": 1, "lobe": 0.28},
        },
        # **The finish basin - specified by its crest, because the ground
        # under it is not level.** The finish stands on a promontory: the mesa
        # is at y = -2 and the ground falls to -82 within forty units in every
        # direction the finish camera looks. So `crown` names where the rim
        # should *reach*, fourteen above the finish deck, and each mass grows
        # from wherever the ground is to get there. The far wall comes out
        # about eighty units tall and the near horn about twenty-five, and the
        # two read as one rim rather than as a tall rock and a short one.
        #
        # The arc runs 26 to 158 degrees around a centre four units past the
        # finish, which is the wedge both finish cameras look into and is open
        # on the approach: nothing here can come between a camera and the
        # FINISH board. Seven of the thirteen frames see it.
        "finish": {
            "kind": "basin", "offset": [4.0, 8.0], "count": 5,
            "radius": 30.0, "from": 26.0, "to": 158.0, "fall": 0.42,
            "crown": 14.0, "fall_y": 26.0, "min_aspect": 1.6,
            "height": 46.0, "base": 17.0, "sink": 5.0, "seed": 1709,
            "kits": ["cliff", "wall", "cliff", "block", "ledge"],
            "material": "world_warm_rock",
            "shape": {"ledges": 2, "buttress": 2, "lobe": 0.42},
        },
        # **And the lower rim, down in the gorge.** The high arc puts rock
        # across 59% of the top third of the finish frame and *nothing* below
        # it - measured, not guessed: a render with the landmarks disabled
        # differs from one with them in zero pixels below y = 700.
        #
        # This second arc stands on the gorge floor at two thirds the radius
        # and tops out twelve *below* the deck, so the drop past the finish
        # gets a shape without anything rising into the payoff. Dark on
        # purpose - `world_damp` is the darkest surface in the world, and the
        # brief asks the finish for "a dark lower ravine beneath". A dark
        # ravine with form in it is a different picture from a dark ravine
        # with nothing in it.
        "finish_floor": {
            "node": "finish", "kind": "basin", "offset": [4.0, 8.0],
            "count": 4, "radius": 21.0, "from": 40.0, "to": 150.0,
            "fall": 0.4, "crown": -12.0, "fall_y": 22.0, "min_aspect": 1.4,
            "height": 30.0, "base": 13.0, "sink": 4.0, "seed": 1801,
            "kits": ["wall", "cliff", "wall", "block"],
            "material": "world_damp",
            "shape": {"ledges": 2, "buttress": 1, "lobe": 0.36},
        },
    },
}

# **Six practicals, three of them warm and all of them at the finish end.**
#
# V25 had three at a fifth of a zone practical's energy. These add a warm pair
# inside the finish basin and one on the merge wall, and the energies stay
# where V25 put them for the same reason V25 put them there: a dark world will
# take any amount of light before it looks full, and the frame where it starts
# looking full is the frame where the machine has stopped being the brightest
# thing in it.
LAMPS = {
    "sites": [
        ["obstacle", -22.0, -9.0, -6.0, "#FFB469", 0.9, 26.0, 1.6],
        ["split", 26.0, -16.0, 8.0, "#7FD8FF", 0.7, 30.0, 1.7],
        ["merge", -20.0, -7.0, 4.0, "#8FD0F0", 0.6, 24.0, 1.7],
        ["finish", 22.0, -4.0, 18.0, "#FFC98A", 1.1, 28.0, 1.5],
        ["finish", -14.0, -6.0, 22.0, "#FFB469", 0.8, 24.0, 1.6],
        ["finish", 4.0, -14.0, 34.0, "#FFD3A0", 0.7, 30.0, 1.5],
    ],
}


# --- D: material zones on the near ground -----------------------------------
#
# `[dx, dz, radius, material]`, terrain-relative. Eleven zones over a course
# 200 units long, so a zone is 28 to 34 units across and the variation is at
# the scale of a hillside rather than of a texel - which is the brief's Part B
# rule, and the reason this is geometry rather than a noise map.
#
# **Sited against the frames, like the landmarks.** The first ten were placed
# at the race nodes, and four of them landed in no frame at all: the ground a
# camera sees is not the ground beside the node it is named for. Each row
# below names the frames the instrument puts it in.

PATCHES = {
    "rings": 7,
    "facets": 13,
    "lift": 0.1,
    "skirt": 1.1,
    "rough": 0.3,
    "sites": [
        # The start shelf itself, under the grid - the bottom of the start and
        # mixer frames, where the ground is a third of the picture.
        at(-20.0, -38.0) + [15.0, "world_bench"],
        # The bench the launch runs along: mid-frame at the start, left at the
        # mixer.
        at(4.0, -18.0) + [17.0, "world_gravel"],
        at(-12.0, -34.0) + [14.0, "world_gravel"],
        # Beside the spinner corridor: the whole middle of the obstacle frame,
        # which is otherwise one flat blue surface behind the machine.
        at(-9.0, 2.0) + [16.0, "world_gravel"],
        near("obstacle", 20.0, 6.0) + [22.0, "world_damp"],
        near("split", -14.0, -2.0) + [22.0, "world_bench"],
        near("split", 26.0, 6.0) + [24.0, "world_damp"],
        near("merge", -12.0, 4.0) + [24.0, "world_bench"],
        near("finish", -16.0, 6.0) + [26.0, "world_gravel"],
        near("finish", 6.0, 16.0) + [22.0, "world_ember"],
        # **The finish mesa, and the reason the finish frame needed one.** The
        # lower half of that frame is not the gorge - it is the mesa itself at
        # thirty to forty units, seen at a shallow angle, and it was the one
        # large flat area left in the film. This is the warm-neutral ground
        # the payoff stands on.
        at(20.0, 45.0) + [17.0, "world_ember"],
    ],
}

PROFILE = {
    "id": "aurora_valley_v251",
    "title": "Aurora Valley V25.1 - world art",
    "family": "valley",
    "summary": (
        "V25 B's layout and density, rebuilt from a faceted rock kit and a "
        "tiered vegetation kit: stylised material zones on the near ground, "
        "cut benches instead of scattered blocks, five distinct landmarks, a "
        "finish basin and one warm world fill"
    ),
    "extends": "aurora_valley_v25",
    "lights": LIGHTS,
    "world": {
        "enabled": True,
        "patches": PATCHES,
        "walls": WALLS,
        "ridges": RIDGES,
        "scarps": SCARPS,
        "spires": SPIRES,
        "boulders": BOULDERS,
        "anchors": ANCHORS,
        "trees": TREES,
        "landmarks": LANDMARKS,
        "ravine": RAVINE,
        "lamps": LAMPS,
    },
}


# --- the marker -------------------------------------------------------------


def _marker() -> dict:
    """V25.1 painted flat by depth band, for the segmentation.

    Written from `sloped.v251_world.MARKED` so the two cannot drift: a surface
    added to the world and not to that table shows up in the sheet as a hole
    rather than as somebody else's band, which is how V25 found its two
    segmentation bugs.
    """
    from sloped import v251_world

    palette: dict = {}
    for band, keys in v251_world.MARKED.items():
        hue = "#%02X%02X%02X" % v251_world.layer_hue(band)
        for key in keys:
            palette[key] = {"albedo": hue, "unshaded": True, "no_fog": True}
    return {
        "id": "_marker_v251",
        "title": "Marker over aurora_valley_v251 (diagnostic)",
        "family": "diagnostic",
        "summary": (
            "aurora_valley_v251 with every world surface painted the flat hue "
            "of its depth band, so a render of it can be segmented by depth"
        ),
        "extends": "aurora_valley_v251",
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

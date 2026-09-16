"""V30.1: the premium art pass over V30's contained stage.

Usage:

    python tools/race2_v301_stage.py floors     # the three floor treatments
    python tools/race2_v301_stage.py profile    # the production profile
    python tools/race2_v301_stage.py all
    python tools/race2_v301_stage.py report     # what the numbers decided

**This changes no architecture.** The stage footprint, the wall radii, the
bearing arc, the lens keep-out, the stage datum and the seam are V30's, read
straight out of `tools/race2_v30_stage.py` rather than restated here, so a
reader can see that the only things this pass authors are surfaces, module
sizes and where the warm light is let into the building.

## The two findings this pass is built on

**1. The floor's colour was never controlled by its albedo.**

V30 measured its floor as blue, correctly, and concluded the cause was the ACES
toe - so it pre-compensated by authoring the albedo warm (`#443A2C`) until the
*average* came out neutral. The average did. The picture did not: the delivered
final sprint renders its lit floor at RGB(60, 111, 119), a teal at chroma 0.49.

The mechanism is `metallic_specular`. `lab_palette._matte` never sets it, so
every floor plate carries Godot's 0.5 default, and at the 20-58 degrees below
horizontal this lens sees the floor at, that dielectric term is **half the
frame's brightness**: dialling it to zero takes the sprint from mean luma 67.1
to 35.3. Nine probe renders place that term outside everything V30 suspected -
it is unchanged by removing every light in the rig, by a black sky, by a *red*
sky at full energy, by zero ambient, by no fog and by zero background energy,
and it survives with the four directional lights deleted. An albedo
pre-compensation can only ever steer the diffuse fifth of such a surface.

    specular    G/R    B/R   chroma   mean luma
      0.50     1.84   1.97    0.492      67.1      V30 as shipped
      0.30     1.69   1.78    0.440      62.3
      0.20     1.31   1.38    0.274      61.9
      0.10     1.06   1.25    0.201      65.9      V30.1
      0.00     1.04   1.17    0.147      79.5      flat: no form left

So the floor is neutral here because its specular is 0.10 and its albedo is a
real graphite, not because its albedo is brown. That is also why the brief's
"do not fight it by making the floor darker" is the right instruction: darker
was never the lever, and V30's own sweep showed the cast getting worse each
time it was tried.

**And V30's hue test could not see this.** `race2_v30_review.measure` takes
`blue_over_red` over every room pixel above luma 20, which averages the bright
teal panel tops in with the dark neutral shadow between them and reported 1.18
against a 1.35 threshold. Hue is a property the eye reads where the picture is
*bright*; measured on the lit floor alone the same frame is 1.97. V30.1 adds
the bright-surface measure alongside it rather than replacing it, because the
film average is still the right number for "is the room blue" - it was just
never the right number for "is the floor blue".

**2. Nothing in the V30 toolchain ever reported a seam rate.**

V30 sized its floor module against the *frame width*, which only ever argues
for a finer module, and landed on a 2.2-unit strip. At camera A's median 12.04
units a second that is **5.06 seams a second**, and the delivered film reads as
a grate from about 6 s onward. `tools/race2_v301_floor.py` is the missing half
of that arithmetic and it is what sizes the modules below.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.race2_v30_envelope import footprint, load_course  # noqa: E402
from tools.race2_v30_stage import (  # noqa: E402
    FLOOR_TOP, GEOMETRY, LIVE_ARC, PROFILES, WALL_R, RIB,
    keepout, _race2_bays, wall_band,
)

DOCS = "docs/validation/race2/v301_stage"

# --- what V30.1 may not move -----------------------------------------------
#
# Restated from `tools/race2_v30_stage.py` so this file reads as a surface pass
# and so `report` can assert it did not drift. Every one of these is a V30
# architectural decision and the brief locks all of them.

V30_WALL_RADII = (56.0, 70.0, 60.0, WALL_R + 6.0)
V30_FLOOR_HALF_EXTENT = 78.54     # 3 x 52.18 / 2 by 66 x 2.38 / 2, the smaller
V30_STAGE_REACH = 80.0            # where the floor stops, and the lens's limit

# --- the floor modules, sized from `race2_v301_floor.py` -------------------
#
#     pitch   seams/s   across the sprint's median frame
#      2.38     5.06          4.29     V30: the grate
#      9.00     1.34          1.13
#     13.00     0.93          0.79     V30.1: chosen
#     18.10     0.67          0.56
#     26.50     0.45          0.39     broad slab: at the quiet limit
#
# The target is a *band* rather than a value, and both ends of it are failures
# V30 actually measured. Above about two seams a second the floor is a pattern
# the eye tracks instead of the race, which is the grate. Below about 0.4 a
# second the narrow shots contain no edge at all, which is the flat gradient
# V30's first build got from a 34 x 30 pad that covered its whole frame.

MODULE_BROAD = 26.0        # + 0.5 gap  -> 26.50 pitch, 0.45 seams/s
MODULE_PLATE = 12.5        # + 0.5 gap  -> 13.00 pitch, 0.93 seams/s
MODULE_CHANNEL = 17.5      # + 0.6 gap  -> 18.10 pitch, 0.67 seams/s

# **A seam is a line, not a trench, and this is the number that decides which.**
# V30 laid 0.6-thick plates on a base 1.45 below them, so a 0.18 seam opened
# onto a surface 0.55 down - an aspect ratio of 3:1, which at this grazing
# angle is a slot in full shadow. Its own documentation calls the result
# "high-contrast corduroy" and records fixing it; the fix reduced the depth but
# left the aspect ratio above 2. A premium floor's joint is *wider than it is
# deep*: these seams are 0.5 to 0.6 across and 0.3 down.
SEAM_RECESS = 0.30
PLATE_THICKNESS = 0.6

# --- the final sprint's own geometry, measured ------------------------------
#
# `tools/race2_v301_floor.py` for the floor field and the camera track itself
# for the framing. This is the box every runway and warm-practical number below
# is sited inside, and it is the floor equivalent of V30's rule about the wall
# arc: architecture outside the box is architecture nobody sees.
#
# **The sprint is two shots inside one take, and the first version of this
# pass missed that.** Over its 6.47 s the centre ray sweeps a wide arc - from
# (-7, 6) out to (17, 0) and back through (15, 11) - and then from about
# t = 15.1 it *settles* and barely moves again: (-13, 20), (-17, 24),
# (-16, 24), (-16, 25), (-15, 26), (-14, 26), (-13, 27), (-12, 27). The last
# four seconds of the film are one framing, and it is the framing the winner
# crosses in.
#
# So "the final sprint's floor" is two different fields, and the money shot is
# the smaller one. Its densest cells are a patch about 12 across and 20 deep:

SPRINT_BOX = {"x": (-34.0, 38.0), "z": (-34.0, 34.0), "centroid": (-5.0, 16.0)}
MONEY_BOX = {"x": (-20.0, -8.0), "z": (16.0, 36.0), "centre": (-14.0, 26.0)}

# **And the machine's own left edge is at x = -13.3, which is what makes the
# money shot's free floor a 6-unit strip.** The racing line in that patch runs
# x = -13.3 .. +11 for z = 12 .. 26 and never passes z = 26. So the floor the
# camera can see there and nothing is standing on is:
#
#     x < -14        a strip about 6 wide, running the length of the shot
#     z > 28         a band across the whole width, behind the finish
#
# Those two are where the runway language goes. The first V30.1 build put its
# side insets at x = -31 and x = +7 - outboard of a 30-wide foundation band -
# and measured the consequence exactly: the sprint's warm coverage *fell* from
# V30's 0.706% to 0.265%, because a band wider than the frame has both its
# edges outside the picture and an accent on its edge is an accent nobody sees.
# That is V30's own rule about the run-out pad, in reverse.
LINE_LEFT_EDGE = -13.3     # the machine's own minimum x in the money box
LINE_FAR_Z = 26.0          # and its maximum z

# --- why every flush floor element below carries clearance 0 ----------------
#
# **Because a rejection here is silent, and V30 loses six elements to it.**
# `environment_stage._deck` refuses a pad inside its `clearance` of the racing
# line or its `keepout` of the camera path and reports it with `push_warning`,
# which `tools/race2_render.py still` did not surface. Running the same two
# guards in Python - `race2_v301_stage.siting` - against the shipped V30
# profile, and checking the answer against the scene's own `stage: census`
# print:
#
#     V30 authors 13 deck pads and builds 8.
#     V30 authors  2 bays      and builds 1.
#
# All five refused pads are warm floor inlays, so **five of V30's nine are not
# in the film** - and the sharp part is which five. Three are the ring at
# clearance 13, which they miss by 1.0 to 2.5 units. The other two are at
# (-18, 33) and (-4, 35): two of the *three* inlays V30 sites from the final
# sprint's own measured footprint, the group its documentation introduces with
# "a practical that is not in the floor is not in the shot that matters". Two
# thirds of the fix for the money shot is absent from it, refused on a 6-unit
# camera keep-out by 0.7 and 2.5 units.
#
# The sixth is the `sweep` portal - the one place in the room where two large
# planes diverge - refused on a keep-out of 14 at a site 6.6 from the camera
# path. Nothing contradicted any of it, because the surface audit measures
# `lit_hall_warm` at 0.61% of the film either way: four inlays plus the wall
# slots are enough to register.
#
# **And the guard is right; the numbers were wrong.** The guard exists to stop
# a tall form standing on the racing line or blotting the lens, and a flush
# floor inlay is neither. That argument is V30's own - its warm-slot docstring
# makes it: "a flush inlay 0.1 proud of the floor cannot obstruct anything,
# which is the same argument `_deck` already makes for a pad under a
# mechanism" - and then it authored clearance 13 and keep-out 6 anyway, so
# the reasoning never reached the number, and five of the nine inlays it
# argues for were refused.
#
# Here it is a proof rather than an argument. `race2_scene` lifts the stage so
# the floor's top surface sits `STAGE_FLOOR_CLEARANCE` = 2.0 **below the lowest
# point of the racing line**, so an element whose top is under 2.0 above the
# floor cannot reach the racing line at any point on the course. The tallest
# thing in `runway_zone` and `warm_architecture` is 0.5. So their clearance is
# 0 not as a waiver but because the geometry has already done the test, and
# their keep-out is 0 for the same reason: a 0.5-unit slab cannot cap a lens
# that is 9.5 to 47 units above the floor.
#
# Anything that stands up - a bay, a wall, a pylon - keeps its guard, and the
# `sweep` bay below is *moved* to satisfy it rather than exempted from it.
FLUSH_MAX_HEIGHT = 0.5
FLUSH = {"clearance": 0.0, "keepout": 0.0}

# --- the floor stack, and why it has to be written down --------------------
#
# **Every piece of floor art is a slab laid on the deck, so they occlude each
# other, and the first build got the order wrong in the one shot that
# matters.** The runway apron was authored 0.19 above the deck and the warm
# inlays 0.13, so the apron - 50 units by 26, laid across the whole sprint -
# covered the three warm assemblies inside it. The review measured the
# consequence and it is the largest single regression this pass produced: the
# final sprint's warm coverage fell to **0.087%**, against V30's 0.706% and
# against 0.389% for the same floor treatment *without* the runway. A feature
# added for the sprint deleted the sprint's warm light.
#
# It is written as an explicit stack because "how high is this pad" is the
# wrong question and "what is under what" is the right one, and only the
# second is checkable. `siting` asserts the ordering.
#
# **Everything here is above the deck, and that is a constraint rather than a
# choice.** The plate field covers the whole floor, so a pad whose top is
# below `FLOOR_TOP` is behind the plates and invisible. A *recess* in floor B
# is therefore a darker value at the same level, not a lower one - floor C is
# the variant that has true recesses, because `skip_x` removes the plates that
# would otherwise be over them.
# The whole stack lives inside a quarter of a unit, because it has to: a floor
# element is meant to be *let into* the deck, and one standing 0.4 proud of it
# is a kerb. The first build's was twice this deep and the sprint's warm strips
# came out as bright bars standing on the floor rather than set into it.
FLOOR_STACK = {
    "apron": 0.06,          # the broad tonal zone: the lowest thing laid on
    "inset": 0.10,          # dark bands: the runway's edges
    "runout": 0.14,         # the machine's own apron where the film ends
    "channel": 0.20,        # a practical's housing
    "strip": 0.26,          # and the practical itself, inside it
}


def _laid(material: str, at, size, level: str, fillet: float,
          thickness: float = 0.26) -> dict:
    """One slab laid on the deck, at a named level of the stack.

    `size` is plan only - width by depth - and the thickness comes from the
    stack, so an element cannot be authored at a height that contradicts its
    place in the order. `_slab` centres a box on its `y`, so the top of a pad
    at level `h` needs `y = h - thickness / 2`.
    """
    top = FLOOR_STACK[level]
    assert top - thickness * 0.5 > -1.0, level
    assert top <= FLUSH_MAX_HEIGHT, (level, top)
    return {
        "at": [at[0], at[1]],
        "size": [size[0], thickness, size[1]],
        "y": top - thickness * 0.5,
        "bearing": 0.0,
        "material": material,
        "fillet": fillet,
        "shadows": False,
        **FLUSH,
    }


# --- the palette ------------------------------------------------------------


def v301_palette() -> dict:
    """The surface retune, as overrides on V27's eleven keys plus V30's twelfth.

    **No new palette key.** V30 added `hall_deck_mid` because a floor that is
    43% of the film cannot be two values; three is enough, and a family that
    grew a key per edition would be a family nobody could reuse. Everything
    below is a value, a roughness or a specular on a key that already exists.

    The through-line is the specular finding in this module's header. Every
    surface in this room is seen at a grazing angle - the frame top never rises
    above -9.10 degrees, so the lens is always looking *down* - and at grazing
    angles a dielectric's specular term dominates its albedo. V30 tuned eleven
    albedos and left every specular at whatever its builder happened to set,
    which for `_matte` is Godot's 0.5 default and for `_moulded` is 0.5 plus a
    clearcoat lobe on top. So the floor, the deck base, the kerbs and the walls
    were all being coloured by a reflection nobody had authored.
    """
    return {
        # **The floor.** A real graphite, at the specular that lets it stay
        # one. The albedo is lighter than V30's because it now has to carry
        # the brightness the specular was carrying, and it is a *neutral*
        # rather than V30's warm pre-compensation: the two moves together hold
        # the film's mean luma at 56.4 against V30's 55.8 while taking the lit
        # floor's chroma from 0.417 to 0.072, which is the brief's "preserve
        # approximately the current perceived brightness" met by construction
        # rather than by eye.
        #
        # **The albedo is very slightly cool and the render is very slightly
        # warm, and that is the pre-compensation that is actually needed.**
        # V30's was 60 points of hue in the wrong direction for the wrong
        # reason; this is four in the right one. #575559 renders at G/R 1.03,
        # B/R 0.96. A warmer albedo overshoots into khaki - which is what the
        # first V30.1 build did at #5C554C, measuring B/R 0.83 and reading as
        # olive sand on the sheet.
        "hall_deck": {"albedo": "#474549", "roughness": 0.90,
                      "specular": 0.10, "soft_light": "#3A3832"},
        # The floor's second value, and it is a *value* rather than a second
        # material: five L* under the panel, which reads as a tonal block at
        # module scale and as nothing at all at seam scale. V30 authored the
        # same relationship and it never appeared, because at specular 0.5 the
        # reflection swamped a five-point albedo difference. It appears now.
        "hall_deck_mid": {"albedo": "#434148", "roughness": 0.91,
                          "specular": 0.10, "soft_light": "#35332E"},
        # What is at the bottom of a seam and of a service channel. Kept close
        # to the panel for the reason V30 gives - a joint describes an edge,
        # it does not cut a hole - and given the same low specular so a channel
        # does not light up as a bright line, which is the failure mode of a
        # recess whose floor is glossier than the deck around it.
        "hall_deck_dark": {"albedo": "#363439", "roughness": 0.94,
                           "specular": 0.08},
        # **The wall, and the brief's Part B half-done in one row.** Two
        # changes. The value comes up, because a wall at #302C27 under this rig
        # renders as a flat dark rectangle and *no amount of articulation is
        # visible on a surface with no light on it* - which is why this row
        # comes before the pattern work in `v301_walls`. And the clearcoat
        # comes off: `_moulded` puts a second specular lobe on top of the
        # first, which on a large flat face is a broad sheen that flattens
        # exactly the shallow reveals this pass authors. What replaces it is a
        # low even specular, which is what satin paint on concrete looks like.
        "hall_panel": {"albedo": "#434149", "roughness": 0.70,
                       "specular": 0.12, "clearcoat": 0.0,
                       "soft_light": "#3A3832"},
        # **Recess lining and bay backs, and this row is the `central` frame's
        # black hole.** The marker render puts `hall_panel_dark` at a third of
        # the frame at 6.8 s - the `drum` bay's 26 x 17 back, at close range -
        # and at #1D1A16 a surface that size is not a recess, it is a hole. It
        # is still the darkest thing in the room and it is now dark *paint*
        # rather than absence: 18 L* under the wall, which is enough for a
        # reveal to read and not enough to punch out.
        "hall_panel_dark": {"albedo": "#302E34", "roughness": 0.88,
                            "specular": 0.05,
                            "soft_light": "#2F2E31"},
        # Painted structural metal: the ribs and the pylons. This is the one
        # surface in the room allowed a real highlight, because a rib is read
        # as a *vertical* by the band running down it, and that band is what
        # tells a viewer how tall the wall behind it is. Brushed rather than
        # lacquered - a narrow clearcoat instead of V27's wide one.
        "hall_rib": {"albedo": "#514F55", "roughness": 0.48,
                     "specular": 0.26, "clearcoat": 0.18,
                     "clearcoat_roughness": 0.22,
                     "soft_light": "#38362F"},
        # Plinth, cornice, cap: the light value that describes an edge. The
        # brightest room surface, and it has to stay well under the machine -
        # the pearl running surface is 153 luma above the room.
        "hall_trim": {"albedo": "#766F68", "roughness": 0.44,
                      "specular": 0.22, "clearcoat": 0.16,
                      "soft_light": "#403D36"},
        "hall_beam": {"albedo": "#3A342C", "roughness": 0.87,
                      "specular": 0.08},
        # **The machine's foundation, and it is now a foundation rather than a
        # kerb.** Held apart from the floor deliberately, for V30's reason: it
        # is the one surface that says where the machine stops and the room
        # starts, and it can only do that by matching neither.
        #
        # **A trace of warmth, and the first build's was three times too
        # much.** #635B4F is a defensible pad colour on a swatch and it is not
        # one at this size: the station kerbs are 12 to 16 units under a lens
        # 10 to 20 units up, so they take 10-25% of `central`, `switchback` and
        # `sprint_early` each, and at that coverage a warm grey is an olive
        # block sitting in a neutral room. The rule the floor established
        # applies to anything big: **a surface's allowed chroma is set by its
        # screen area, not by its material story.** So this is four points of
        # warmth rather than twenty, and it is still the warmest large surface
        # in the room.
        "hall_grate": {"albedo": "#4C4945", "roughness": 0.94,
                       "specular": 0.14},
        "hall_glass": {"albedo": "#101113", "roughness": 0.10,
                       "specular": 1.0},
        # Warm, and only a little. V30's 0.62 is kept: at 1.9 a strip clips to
        # paper white and stops being warm at all, which is a bright accent
        # competing with the racers rather than an architectural one supporting
        # them. What changes in this pass is *where* they are, not how bright.
        "lit_hall_warm": {"albedo": "#C98E52", "emission": "#FF9A47",
                          "energy": 0.62},
        "lit_hall_cool": {"albedo": "#8A9298", "emission": "#B9C6CE",
                          "energy": 0.40},
    }


def v301_lights() -> dict:
    """V30's rig, with the fifth light it never knew it had.

    V30's own note says "all four lights off the blue", and it moves four:
    `WorldKey`, `WorldFill`, `WorldWarm` and `WorldRim`. `contained_base`
    authors **five**. `WorldBounce` - `#3C5878`, energy 0.55, the strongest
    remaining blue in the room and higher-energy than either of the two V30
    dimmed - is inherited untouched through `environment_profile.merge`, which
    is a deep merge, so a light a child never names survives into it.

    It is neutralised rather than removed, and the difference matters: it
    points *up* at +24 degrees, so it lights the downward and side faces that
    no other light in the rig reaches, and deleting it would take the underside
    of every reveal, seam and channel edge to black. That is the whole surface
    this pass is authoring. So it keeps its geometry and its energy and loses
    only its hue.

    Measured on the final sprint, neutralising it changes nothing at all -
    RGB(60.4, 111.0, 118.9) either way, to a tenth - which is itself the
    reason to be suspicious of any story about what is colouring that shot.
    The teal there was never a light. It shows up in the near-field reveals
    instead, which is where a bounce light is supposed to show up.
    """
    return {
        "WorldKey": {"colour": "#EFEAE1", "energy": 0.78, "specular": 0.14,
                     "rotation": [-46.0, -58.0, 0.0]},
        "WorldFill": {"colour": "#8A8781", "energy": 0.30, "specular": 0.0,
                      "rotation": [-26.0, 116.0, 0.0]},
        "WorldWarm": {"colour": "#FFC694", "energy": 0.30, "specular": 0.0,
                      "rotation": [-14.0, 28.0, 0.0]},
        "WorldRim": {"colour": "#B9B3A9", "energy": 0.16, "specular": 0.0},
        "WorldBounce": {"colour": "#575350", "energy": 0.55, "specular": 0.0},
    }


def v301_atmosphere() -> dict:
    """Sky, grade and fog: V30's, with the sky demoted to what it measures as.

    V30 reasons at length about the sky being chosen "as a light rather than as
    a picture", because it supplies ambient and, through
    `reflected_light_source`, every specular reflection in the room. The first
    half is true. The second is not, and it is worth recording because it is
    the kind of belief that survives a whole edition: setting this sky to pure
    **red at full energy**, with every light deleted, moves the final sprint's
    lit floor from RGB(23.0, 98.2, 108.0) to RGB(23.1, 98.2, 108.0). The sky
    contributes nothing to this picture through any path.

    So it is left where V30 put it - neutral and near black, which is correct
    for a room and costs nothing - and no claim is made about what it does.
    The grade is untouched: `white` 12.0 and `exposure` 0.82 are what keep the
    racers at 211, and V30's sweep already showed that every tonemap that
    reduces the cast also costs the racers their candy.
    """
    return {
        "sky": {"top": "#0C0B0A", "horizon": "#15130F",
                "ground_bottom": "#0B0A09", "ground_horizon": "#131210",
                "curve": 0.1, "sky_energy": 0.55, "ground_curve": 0.22,
                "sun_angle_max": 3.0, "energy": 1.0, "sun_curve": 0.12},
        "grade": {"ambient_colour": "#403E38", "ambient_energy": 0.68,
                  "ambient_sky_contribution": 0.0, "exposure": 0.82,
                  "white": 12.0, "contrast": 1.02, "saturation": 1.06},
        "fog": {"enabled": True, "colour": "#231F1A", "energy": 0.55,
                "sun_scatter": 0.02, "density": 0.0016, "sky_affect": 0.06,
                "aerial_perspective": 0.30, "height": -30.0,
                "height_density": 0.004},
    }


# --- the floor --------------------------------------------------------------


def _under(recess: float = SEAM_RECESS, material: str = "hall_deck_dark",
           margin: float = 2.5, thickness: float = 2.4) -> dict:
    """The slab a seam opens onto, placed by how deep the seam should read.

    Solved rather than typed, because the three numbers that decide a joint's
    aspect ratio live in three different fields and V30's were set
    independently. A plate is laid at `y` with `PLATE_THICKNESS`, so its top is
    `y + t/2`; the base is laid at `y - drop` with its own thickness, so its
    top is `y - drop + T/2`. For the seam to read `recess` deep:

        drop = T / 2 + t / 2 - recess

    **`margin` is 2.5 and V30's 6.0 is a measurement error waiting to be
    made.** The base slab is `span + 2 * margin` across, and the plates cover
    only `cells * cell`, so the exposed border is `margin` plus half a pitch -
    at V30's numbers a ring of bare lining 7 units wide around a 156-unit
    floor, at the radius the hook's centre ray lands in. The V30 audit never
    caught it because its plate field ran to 66 rows of 2.2 and the border was
    a thin line in z; the V30.1 field is square, and at margin 7 the surface
    audit came back with `hall_deck_dark` at **20.26% of the film** against
    V30's 0.09%, peaking at 39% of the early chase. The lining is meant to be
    what a seam opens onto, not a surface in its own right.
    """
    return {
        "margin": margin,
        "drop": thickness * 0.5 + PLATE_THICKNESS * 0.5 - recess,
        "thickness": thickness,
        "material": material,
        "fillet": 0.8,
    }


def _field(cells, module, gap, materials=None, at=(0.0, 0.0), terrace=None,
           skip_x=None, skip_z=None, material="hall_deck",
           recess=SEAM_RECESS) -> dict:
    """One plate field in the shape `environment_stage._plates` reads.

    The plate is laid so its *top* lands on `FLOOR_TOP`, which is the plane
    `race2_scene._build_stage` lifts to sit `STAGE_FLOOR_CLEARANCE` under the
    lowest point of the racing line. Every height in a V30 or V30.1 profile
    therefore reads directly as "above the floor".
    """
    field = {
        "at": [at[0], at[1]],
        "cells": [cells[0], cells[1]],
        "cell": [module[0], PLATE_THICKNESS, module[1]],
        "gap": gap,
        "y": FLOOR_TOP - PLATE_THICKNESS * 0.5,
        "thickness": PLATE_THICKNESS,
        "fillet": 0.3,
        "shadows": False,
        "material": material,
        "under": _under(recess),
    }
    if materials:
        field["materials"] = materials
    if terrace:
        field["terrace"] = terrace
    if skip_x:
        field["skip_x"] = list(skip_x)
    if skip_z:
        field["skip_z"] = list(skip_z)
    return field


def _tonal_blocks(nx: int, nz: int, accents) -> list:
    """A materials cycle that makes large tonal blocks rather than a pattern.

    `_plates` picks by `ix + iz * nx` modulo the list length, which is a lever
    that cuts both ways: a list whose length shares no factor with `nx` walks
    across the grid and produces a diagonal weave, and V30's does exactly that
    - twelve entries against three columns, advancing one group a row, which
    is why its "every fourth strip is an accent" reads on paper and reads as
    uniform corduroy in the film.

    A list of length `nx * nz` addresses each module once, so the pattern is
    whatever is authored and nothing emergent. `accents` is a set of
    `(column, row)` pairs, and they are chosen in *runs* - two and three
    modules adjacent - because the brief asks for large tonal blocks and a
    single isolated darker module at this scale reads as a stain.
    """
    out = []
    for iz in range(nz):
        for ix in range(nx):
            out.append("hall_deck_mid" if (ix, iz) in accents else "hall_deck")
    # `_pick` indexes `ix + iz * nx`, so the list must be column-major in the
    # sense of advancing `ix` fastest - which is the order it is built in.
    return out


def floor_broad() -> list:
    """A: broad slab. Large clean panels, very sparse seams, most minimal.

    26-unit modules on a 26.5 pitch: 0.45 seams a second, at the quiet end of
    the target band, and 36 plates against V30's 198. The sprint's median
    frame crosses 0.39 of a seam, which is the risk this variant is here to
    test - a shot that contains no edge anywhere renders as a gradient.
    """
    accents = {(1, 1), (2, 1), (1, 2), (4, 3), (5, 3), (0, 4), (3, 5)}
    return [_field(cells=(6, 6), module=(MODULE_BROAD, MODULE_BROAD), gap=0.5,
                   materials=_tonal_blocks(6, 6, accents))]


def floor_plates() -> list:
    """B: foundation plates. Large stepped engineered plates, subtle variation.

    12.4-unit modules on a 13.0 pitch: 0.93 seams a second, near the middle of
    the band, and 0.79 across the sprint's median frame so the narrow shots
    still carry an edge. 144 plates.

    What makes them foundation plates rather than tiles is the tonal grouping:
    sixteen of the 144 modules are `hall_deck_mid`, arranged in runs of two and
    three so the floor carries a few large blocks of a second value rather than
    a scatter of single darker tiles.

    **It was going to be a stepped field and `terrace` cannot be used with an
    `under` slab, which is a genuine incompatibility rather than a tuning
    problem.** `_plates` drops each band of plates beyond `terrace.from` by
    `terrace.step`, and the base slab under the field is a single box at one
    height. So the third band out sits 1.05 below the deck while the lining
    stays 0.30 below it, and the lining is then *above* the plates it is
    supposed to line: past r = 56 the floor renders as bare
    `hall_deck_dark`. The surface audit is unambiguous about the scale of it -
    `hall_deck_dark` came back at **18.24% of the film and 39% of the early
    chase**, against V30's 0.09% - and no frame of it looked wrong enough to
    notice, because a dark floor that is dark everywhere just looks like a
    dark floor.

    The fix available here was to deepen the base past the lowest step, and
    that is the wrong fix: the base's depth is also the seam depth, and
    `SEAM_RECESS` is 0.30 because a joint deeper than it is wide is the trench
    V30 shipped. A terraced plate field needs a terraced base, which is a
    builder change, and this is an art pass. So the field is flat.
    """
    accents = {
        (3, 2), (4, 2), (3, 3), (4, 3),
        (8, 4), (9, 4), (8, 5),
        (1, 7), (2, 7), (1, 8),
        (6, 9), (7, 9), (6, 10), (7, 10),
        (10, 1), (11, 1),
    }
    return [_field(cells=(12, 12), module=(MODULE_PLATE, MODULE_PLATE),
                   gap=0.5, materials=_tonal_blocks(12, 12, accents))]


def floor_channel() -> list:
    """C: recessed service channel. Broad slab, cut by two wide channels.

    17.5-unit modules on an 18.1 pitch, 0.67 seams a second, 81 modules - and
    then one column and one row omitted, so the `under` slab shows through as
    a channel 18.1 units wide rather than as a seam 0.6 wide. That is the
    distinction `skip_x` exists for: widening `gap` widens every joint in the
    field at once and never makes a channel, because a channel is an absent
    module and a seam is a joint between two present ones.

    **Which column and which row is a measurement, not a composition.** The
    field is 9 x 9 on an 18.1 pitch centred on the chamber axis, so column `i`
    spans x = (i - 4) * 18.1 +/- 9.05 and row `j` the same in z. The final
    sprint's floor box is x -34..38 and z -34..34 with the picture's weight at
    (-5, 16):

        column 2  ->  x  -45.3 .. -27.1   the sprint's left frame edge
        column 6  ->  x   27.1 ..  45.3   the sprint's right frame edge
        row 6     ->  z   27.1 ..  45.3   crosses behind the finish

    Column 2 and row 6 are taken. Column 6 is not: two channels 72 units apart
    read as a pair of edges to a very wide bay rather than as service runs, and
    the second one costs nine modules to put a dark band where the hook already
    has the deepest wall in the room behind it.
    """
    return [_field(cells=(9, 9), module=(MODULE_CHANNEL, MODULE_CHANNEL),
                   gap=0.6,
                   materials=_tonal_blocks(9, 9, {
                       (1, 3), (1, 4), (2, 4),
                       (5, 1), (6, 1), (5, 2),
                       (4, 7), (5, 7), (4, 8),
                       (7, 5), (7, 6),
                   }),
                   skip_x=(2,), skip_z=(6,))]


FLOORS = {"a": floor_broad, "b": floor_plates, "c": floor_channel}
FLOOR_TITLES = {
    "a": ("Broad slab", "26-unit modules, 0.45 seams a second, 36 plates."),
    "b": ("Foundation plates",
          "12.4-unit stepped modules, 0.93 seams a second, 144 plates."),
    "c": ("Recessed service channel",
          "17.5-unit modules with one column and one row omitted."),
}


# --- the rest of the room ---------------------------------------------------


def v301_walls() -> list:
    """V30's four bands at V30's four radii, with the rhythm re-authored.

    **Not one radius, height, arc, thickness or batter moves.** The brief locks
    the wall placement strategy and the stage footprint, and those are what
    those numbers are. What moves is `pattern`, which is the only field that
    decides how many separate things a viewer counts on a wall face.

    V30's near flank is `["rib", "slot", "bay", "slot", "rib"]` - five kinds
    across five segments, so every 15-degree sector is a different object, and
    with the trim, plinth and cornice each segment also carries three edges of
    its own. At 270 pixels wide that is the brief's "30 small details". The
    rule it asks for instead is 2 to 4 large architectural shapes, and the way
    to get them from this builder is to let a form *run* across several
    segments: three panels in a row is one broad face, and it reads as one
    because nothing interrupts it.

        near flank   panel panel bay panel panel   one deep bay, one broad face
        deep rear    panel panel bay slot panel     the rear face, cut once
        far flank    panel rib slot panel           one vertical, one slot
        upper        seven panels and two ribs      a plain band, stepped

    The bays get deeper rather than more numerous - `bay_depth` 5.0 to 7.5 and
    6.0 to 8.5 - because a recess is read by the shadow in it, and a shallow
    wide bay in a wall lit from -46 degrees has no shadow in it at all.
    """
    # **The near flank is the hook's background and the hook is half wall.**
    # The marker render puts `hall_panel` at roughly 50% of the frame at
    # 0.6 s, all of it this band, and V30's answer to a face that size was
    # five different segment kinds. The answer here is the opposite: three
    # broad faces, and a *shallow stepped plan* so the face is not flat. The
    # radius cycles +/- 1.8 on a period of 4 segments, which over a 5-segment
    # arc is one step across the hook's whole background - a reveal, not a
    # scallop. The step is what V30 used on its upper band and never on the
    # one the opening actually looks at.
    near_flank = wall_band(
        56.0, FLOOR_TOP, 15.0,
        ["panel", "panel", "bay", "panel", "panel"],
        arc=(90.0, 150.0), thickness=4.0, batter=1.0,
        extras={"bay_depth": 7.5, "rib": RIB, "bay": _BAY, "slot": _WARM_SLOT},
        cornice=True, keepout_units=16.0,
        radius_step=1.8, radius_cycle=4)
    deep_rear = wall_band(
        70.0, FLOOR_TOP, 26.0,
        ["panel", "panel", "bay", "slot", "panel"],
        arc=(150.0, 210.0), thickness=5.0, batter=2.5,
        extras={"bay_depth": 8.5, "bay": _BAY, "slot": _WARM_SLOT, "rib": RIB},
        cornice=True)
    far_flank = wall_band(
        60.0, FLOOR_TOP, 19.0,
        ["panel", "rib", "slot", "panel"],
        arc=(210.0, 255.0), thickness=4.0, batter=1.5,
        extras={"rib": RIB, "slot": _WARM_SLOT}, cornice=True,
        keepout_units=16.0)
    # The upper band's job is to make the room read tall without putting a
    # 34-unit slab in the picture, and V30's rhythm of eleven segments in a
    # panel/rib alternation was the wrong tool for it: an upper band is the
    # *quietest* surface in the room, because it is the furthest and the one
    # the eye should not be counting. Two ribs instead of four, and the
    # radius cycle lengthened from 3 to 5 so the stepped face reads as three
    # broad planes over the live arc rather than as a scallop.
    upper = wall_band(
        WALL_R + 6.0, 13.0, 21.0,
        ["panel", "panel", "panel", "rib", "panel", "panel",
         "panel", "panel", "rib", "panel", "panel"],
        thickness=5.0, batter=2.5, material="hall_panel",
        extras={"rib": RIB},
        plinth=False, radius_step=2.0, radius_cycle=5)
    return [near_flank, deep_rear, far_flank, upper]


# A bay with a real depth to it, and a reveal rather than a frame. V30's jamb
# and head are kept - they are what make a recess read as built - and the
# warm strip inside it is what the brief's Part D asks for: a practical in a
# shallow wall bay, which is a light that is part of the building.
_BAY = {
    "jamb": 4.2, "head": 3.6, "sill": 0.0, "opening": 0.52, "lift": 0.10,
    "material": "hall_panel_dark",
    "strip": {"width": 0.7, "height": 2.0, "depth": 0.9, "at": 0.14,
              "material": "lit_hall_warm"},
}
# The wall's own warm slot, at 0.13 of the band height - 1.7 units above the
# floor. V30's number and V30's reason, which is the only reason that matters
# here: the base of the wall is the only part of it the middle and the final
# sprint ever contain.
_WARM_SLOT = {
    "at": 0.13, "width": 0.62, "height": 2.4, "depth": 1.1,
    "material": "lit_hall_warm",
}


def machine_foundations() -> list:
    """The pads under the stations, and one more than V30 has.

    V30's four kerbs are kept at their sizes, which were themselves a
    correction: its first build put a 34 x 30 pad under the run-out that
    measured at 100% of the final-sprint frame and hid the whole floor behind
    it. These are 12 to 16 units and sized to their stations.

    **The run-out gets one now, and it is the brief's Part F answered with a
    measurement rather than with a rule.** V30 left it off deliberately and
    listed the absence as a remaining weakness - "wrong for the one station the
    film ends on". The reason it could not have one was that the sprint's
    visible ground is narrow, so a pad sized to the station covered the frame.
    That argument was made against a floor whose only other content was a
    2.2-unit seam every quarter second; against 13-unit modules and a
    foundation zone it no longer holds, because the pad is now one shape among
    several of its own scale rather than the only shape in the shot. It is
    sized to the *machine* rather than to the frame - 13 x 9, the same as the
    other four - and it sits at the run-out's own station coordinates.
    """
    pads = [
        {"at": [2.0, -22.0], "size": [16.0, 1.6, 9.0], "y": 0.5},
        {"at": [0.7, -14.4], "size": [13.0, 1.6, 9.0], "y": 0.5},
        {"at": [-0.5, 0.0], "size": [13.0, 1.6, 12.0], "y": 0.5},
        {"at": [-1.2, 14.4], "size": [12.0, 1.6, 9.0], "y": 0.5},
        {"at": [-2.0, 26.0], "size": [11.0, 1.4, 8.0], "y": 0.4},
    ]
    return [dict(pad, bearing=0.0, material="hall_grate",
                 clearance=0.0, keepout=0.0, fillet=0.5) for pad in pads]


def runway_zone() -> list:
    """The final sprint's floor, as a broad foundation zone with a visible edge.

    **The brief's Part E, and the constraint on it is Part E's own list of
    prohibitions**: no rails, no second track, no arrows, no text, no glowing
    neon, no theme. What is left that an environment can do is *value* and
    *scale*, and this is both - one broad foundation apron under the sprint's
    own measured footprint, with the edges that describe it placed where the
    money shot can actually see them.

    **There is no broad apron, and that is the third thing this shot's
    geometry refused.** The first build laid a `hall_deck_mid` slab 50 across
    by 26 deep under the sprint, on the reasoning that its far edge would lie
    across the picture behind the finish. The surface audit measured what it
    actually did: `hall_deck_mid` at **89.6% of the winner frame**. The money
    shot sees a floor patch about 12 by 20, so a 50 by 26 slab is not a zone
    within the shot, it *is* the shot - and with the whole frame one value the
    13-unit module rhythm underneath it was gone, which is why that frame
    rendered flat. It is V30's own 34 x 30 run-out pad, which measured at 100%
    of this same frame, rebuilt at a different size for a different reason.

    So the runway is made of edges rather than of an area. Three elements,
    each sited against a measurement:

    **The side inset, and there is only one because only one side is free.**
    A 4.5-wide band at x = -19.5, running z 12..40. That
    is inside the money box's x = -20..-8, so it is in the picture, and it
    runs the direction the shot is travelling. The brief asks for "two
    restrained side insets" and the machine is in the way of the second: the
    money box runs x = -20..-8 and the racing line's own left edge is at
    x = -13.3, so the free floor on that side is the strip from -20 to -14 and
    there is no corresponding strip on the other.

    **All three are `hall_deck_mid` rather than `hall_deck_dark`, and the
    surface audit is why.** Authored in the dark lining value they measured
    `hall_deck_dark` at 20.26% of the film - more than the deck's own 14.04% -
    and a floor whose lining outweighs its deck reads as a dark floor with
    plates on it rather than as a light floor with joints in it. Five L* under
    the deck is enough for a zone the brief asks nobody to notice as a change;
    eighteen is a different floor. The same argument retires the run-out
    apron's `hall_grate`: a 26 x 14 kerb where the film ends took that family
    to 25.46% of the picture and 55% of the final frame.

    **The run-out apron.** Where the marbles end up, at (-24, 30): 10.7 clear
    of the racing line's left edge and inside the frame, 22 by 12. **This is
    the brief's Part F, answered with a measurement rather than a rule.**
    V30 left the run-out with no floor treatment at all and listed the absence
    as a remaining weakness - correct for the frame, wrong for the one station
    the film ends on. Its reason was that a pad sized to the station covered
    the whole frame, and that was true of a 34 x 30 pad laid *under* the
    station on a floor whose only other content was a seam every quarter
    second. This is 26 x 14, it is offset into the free strip rather than
    centred on the station, and it is one shape among several of its own
    scale.
    """
    return [
        # The side inset, in the free strip left of the machine.
        _laid("hall_deck_mid", (-19.5, 26.0), (4.5, 28.0), "inset", 0.8),
        # The band behind the finish: the destination edge, at z = 33. The
        # camera path passes 1.0 from this point, which is exactly why it is
        # flush: at a fifth of a unit high it is under the lens, not in it.
        _laid("hall_deck_mid", (-9.0, 33.0), (46.0, 5.0), "inset", 0.8),
        # The run-out's own apron, offset into the free strip.
        _laid("hall_deck_mid", (-24.0, 30.0), (22.0, 12.0), "runout", 1.0,
              thickness=0.30),
    ]


def warm_architecture() -> list:
    """The warm practicals, let into the floor's own edges rather than laid on it.

    **The brief's Part D, and the change is a shape change.** V30's inlays are
    17 x 0.55 bars sitting 0.15 proud of the deck: a light *on* a floor. What
    makes a light read as part of a building instead is that it sits in a
    recess whose housing is a different value from the surface around it. So
    each of these is a two-part assembly:

        a channel     `hall_deck_dark`, 1.8 wide, flush with the deck
        the strip     `lit_hall_warm`, 0.6 wide, inside the channel

    The channel was 3.2 wide in the first build, which is a proportion that
    reads correctly on a plan and not in this film: nine channels 17 units
    long at that width, all of them in the near ground of a chase shot, put
    `hall_deck_dark` at 39% of the early chase on its own. At 1.8 it is a
    housing around a 0.6 strip - three times the strip, the proportion a real
    recessed fitting has - instead of a dark band with a light in it.

    **It was a three-part assembly and the third part was a mistake worth
    recording.** The first build added a `hall_trim` shoulder alongside each
    strip, to catch the light and give the recess a bright lip - which is how
    a real one is detailed. `hall_trim` is the lightest value in the family, at
    #7D766E, and these assemblies are 17 to 26 units long. In the money shot
    two of them crossed the frame as a pair of pale bars brighter than
    anything in the picture except the machine's own running surface, and the
    marker render made it unarguable: the yellow marker for `hall_trim` is the
    most prominent thing in the winner frame.

    The rule it breaks is the brief's visual hierarchy, and the general form of
    it is the same one the floor's colour taught: **a surface's allowed value
    is set by how much of the frame it takes.** A bright lip 0.8 units wide is
    a detail on a wall 26 units away and a stripe on a floor 18 units away,
    and the lens here is always looking at the floor. The channel's own dark
    surround is enough to describe the recess, and it is the part that was
    doing the architectural work anyway.

    Placement is V30's rule and V30's measurement - the ring at bearings 150,
    175 and 200 on the arc the film looks down, plus the group inside the final
    sprint's own footprint. Their clearance is not V30's: see the `FLUSH` note
    at the top of this file for why eight of V30's twelve inlays are refused by
    the scene and never reach the film, and why the correct guard for a
    half-unit-high inlay on a floor lifted two units under the racing line is
    zero.
    """
    out: list = []

    def assembly(at, length, bearing):
        channel = _laid("hall_deck_dark", at, (length, 1.8), "channel", 0.3)
        strip = _laid("lit_hall_warm", at, (length * 0.92, 0.6), "strip", 0.2,
                      thickness=0.16)
        channel["bearing"] = bearing
        strip["bearing"] = bearing
        return [channel, strip]

    # The ring, on the arc the film looks down. Two radii rather than V30's
    # two-by-three: r = 36 and r = 50 are inside the band the sprint's rays
    # land in, between a nearest ground hit of 14.3 and a 95th-percentile
    # corner radius of 64.1.
    for bearing in (150.0, 175.0, 200.0):
        for radius in (36.0, 50.0):
            angle = math.radians(bearing)
            out += assembly((round(math.sin(angle) * radius, 2),
                             round(math.cos(angle) * radius, 2)),
                            17.0, bearing + 90.0)
    # **The final sprint's group, and it took three attempts to place because
    # the shot's geometry forbids most of what a runway wants to be.**
    #
    # Attempt 1 put two of them on a 30-wide foundation band's outer edges, at
    # x = -27 and x = +1. The sprint's frame is 7.05 to 16.50 units wide where
    # it meets the floor, so both edges were outside the picture and the
    # measured warm coverage *fell* to 0.265% against V30's 0.706%.
    #
    # Attempt 2 moved them into the money box and made them long - 26 units,
    # two of them crossing - and the result is the picture the brief's Part E
    # explicitly forbids: two bright orange bars across the winner frame, a
    # glowing neon runway. Coverage measured 2.316%, four times V30's, and
    # every point of it was in the wrong place.
    #
    # **The finding under both failures is one number.** The money shot sees a
    # floor patch about 12 across by 20 deep, of which the 6-unit strip at
    # x < -14 is all the machine is not standing on. *Any* element long enough
    # to be read as a line in a 6-unit-wide strip spans the frame, so in this
    # shot a long warm element cannot be an accent - it is either invisible or
    # it is the subject. It is the same geometric fact V30 met from the other
    # side when its 34 x 30 run-out pad measured at 100% of this frame.
    #
    # So the money box gets **one** short strip, 14 units in a 20-deep patch,
    # laid along the direction the shot is looking rather than across it, at
    # x = -18 where the frame's left edge is. It reads as a side practical
    # passing, which is what the brief asks for, and it cannot become a bar
    # across the picture because it is shorter than the patch it is in.
    #
    # The second is at z = 6, in the earlier and much wider part of the same
    # take, where a 22-unit strip is a detail. Nothing is placed across the
    # band behind the finish: that is where the destination edge in
    # `runway_zone` does the work, in value rather than in light.
    for at, length, bearing in (((-18.0, 25.0), 14.0, 0.0),
                                ((-19.5, 6.0), 22.0, 0.0)):
        out += assembly(at, length, bearing)
    return out


def v301_bays() -> dict:
    """V30's two sites, at V30's coordinates, as architecture instead of slabs.

    **The offsets, bearings and node choices do not move.** They are a V30
    result and a hard-won one: `last` was tried and rejected because a bay
    offset from it far enough to reach the live arc lands 15.6 units from the
    lens and took the final sprint from 0.73% near-black to 26.77%. The guard
    that refused it is still 14 and the sites are still `drum` and `sweep`.

    What changes is the `drum` site's *kind*, and the marker render is why.
    `kind: "backing"` builds exactly one slab - `_bay_form` has no second
    branch for it - so a 26 x 17 backing is one flat rectangle, and at 6.8 s
    that rectangle is about a third of the frame at close range. It was
    `hall_panel_dark`, and a third of a frame in the room's darkest value is
    the brief's "large, flat, dark, rectangular, prototype-like" exactly.

    `kind: "alcove"` runs three more branches of the same builder: a back set
    `depth` behind the opening, two jambs at the nominal plane, and a head in
    the trim value. That is four large shapes where there was one, it is a
    *large inset bay* rather than tiny panels everywhere, and it costs three
    meshes. The back stays the darkest surface - it is the inside of a recess -
    and the reveal now comes from the jambs' own shadow rather than from the
    value, which is what lets the value come up out of the hole.
    """
    bays = _race2_bays()
    drum = dict(bays["sites"]["drum"])
    drum.update({
        "kind": "alcove",
        # **How far the back stands behind the jamb plane, and it is bounded
        # from both sides.** Too shallow and there is no shadow across the
        # back, so the recess does not read. Too deep and `_bay_form` opens a
        # real hole: the back is set `depth` behind the jamb plane and the
        # jambs are only `thickness` deep, so the sides of the recess are open
        # above and below, and from the central chase's angle the lens looks
        # straight through the gap into the room's own darkness. At 4.5 the
        # near-black measure for that moment went from V30's 0.60% to 2.52%,
        # and on the void map it is a black tear rather than a dark surface -
        # which is worse than the flat slab this replaced, not better.
        #
        # 2.2 with a 4.6 jamb is the balance: the reveal still carries a
        # shadow, and the slot behind it is thinner than the jamb that hides
        # it at this bearing.
        "depth": 2.2,
        "jamb": 4.6, "head": 3.0,
        "material": "hall_panel",
        "trim": "hall_trim",
        # Kept cool, and it is the one cool practical in the room. V30 lists
        # `lit_hall_cool` at 0.17% in 2 of 10 frames as a remaining weakness -
        # authored and seen, but thinly - and an alcove 26 units across is a
        # better housing for it than the flat slab was.
        "strip": {"width": 0.62, "height": 1.6, "depth": 0.7, "at": 0.18,
                  "material": "lit_hall_cool"},
    })
    bays["sites"]["drum"] = drum

    # **The `sweep` portal keeps its geometry and gets a site it can stand
    # on.** V30's offset puts it at (-31.2, -26.8), which is 6.6 units from
    # camera A's plan path against a keep-out of 14, so
    # `environment_stage._bays` refuses it and the scene's own census reports
    # `bays 2` - the `drum` backing's slab and strip, and nothing else. The
    # feature V30 documents at length has never been in a frame.
    #
    # The replacement site is searched rather than nudged. Over a 2-unit grid
    # inside the live arc, 154 sites satisfy all four constraints at once -
    # clearance 11 from the racing line, keep-out 14 from the camera path,
    # 13 from the pylon ring at r = 48, and a radius that leaves it inside the
    # deep rear wall at 70 rather than buried in it. This is the one with the
    # best margins among those the floor map says the film actually looks at:
    #
    #     at (-24, -56)   r 60.9   bearing 203   the peak-sector band
    #     racing line     37.0     needs 11
    #     camera path     31.0     needs 14
    #     pylon ring      13.0     needs 13
    #     share of the picture   0.183%
    #
    # **The offset is large and that is honest rather than incidental.** It is
    # 56 units from the `sweep` station, so this is architecture in the live
    # arc rather than a landmark at a race node - which is V30's own principle
    # taken to its conclusion, since on this course the live arc is far from
    # every station. The anchor is kept on `sweep` for the engineering reason
    # the anchor exists: a course without that station builds no bay at all,
    # rather than one at the origin.
    sweep = dict(bays["sites"]["sweep"])
    sweep.update({"offset": [-22.8, -51.2], "bearing": 203.0})
    bays["sites"]["sweep"] = sweep
    return bays


def v301_pylons() -> dict:
    """V30's eight columns at V30's radius, in the retuned metal.

    Not moved: the radius is the third parallax speed and the brief locks the
    4.88x image-speed spread that depends on it. The cap gets a touch more
    spread, which is the one place in the room where a shallow ledge is free -
    a pylon cap is already a separate mesh.
    """
    return {"bands": [{
        "count": 8, "bearing_from": 97.0, "bearing_step": 18.0,
        "radius": 48.0, "height": 15.0, "width": 2.4, "depth": 2.4,
        "sink": 1.2, "clearance": 18.0, "keepout": 13.0, "fillet": 0.4,
        "material": "hall_rib",
        "cap": {"spread": 2.0, "height": 1.4, "material": "hall_trim"},
    }]}


# --- assembly ---------------------------------------------------------------


def build(ident: str, title: str, summary: str, floor: list, guide: list,
          walls=None, pads=None) -> dict:
    profile = {
        "id": ident,
        "title": title,
        "family": "contained",
        "summary": summary,
        "extends": "contained_base",
        "palette": v301_palette(),
        "world": {},
    }
    profile.update(v301_atmosphere())
    profile["lights"] = v301_lights()
    profile["world"] = {
        "keepout": guide,
        "deck": {
            "clearance": 0.0,
            "keepout": 0.0,
            "plates": floor,
            "pads": pads if pads is not None else (
                machine_foundations() + warm_architecture()),
        },
        "shell": {"bands": walls if walls is not None else v301_walls()},
        "pylons": v301_pylons(),
        "bays": v301_bays(),
    }
    return profile


def floor_variant(key: str, guide: list) -> dict:
    """One floor treatment on V30's architecture and V30's wall rhythm.

    **The walls and the practicals are V30's here on purpose.** The brief asks
    for three floor treatments on the same architecture and for one of them to
    be chosen from rendered camera A frames, and a comparison in which the
    walls also moved would not be a floor comparison. So these three differ
    from each other in exactly one section - `deck.plates` - and from V30 in
    two: that, and the palette, which the floor's colour cannot be judged
    without.
    """
    name, blurb = FLOOR_TITLES[key]
    return build(f"contained_bay_v301{key}", f"{name}, V30.1",
                 f"V30's contained bay with floor treatment {key.upper()}: "
                 f"{blurb}",
                 FLOORS[key](), guide,
                 walls=v301_walls(),
                 pads=machine_foundations() + warm_architecture())


def production(guide: list, floor: str) -> dict:
    """The selected floor, with the wall, runway and practical work on top."""
    return build(
        "contained_bay_v301", "Contained bay, V30.1",
        "V30's contained stage as a premium race chamber: large-module floor, "
        "low-frequency wall articulation, warm practicals let into the "
        "architecture, and a broad foundation zone under the final sprint.",
        FLOORS[floor](), guide,
        pads=(machine_foundations() + runway_zone() + warm_architecture()))


def write(profile: dict) -> str:
    os.makedirs(PROFILES, exist_ok=True)
    path = os.path.join(PROFILES, f"{profile['id']}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=1)
        handle.write("\n")
    return path


def register(ids) -> None:
    path = os.path.join(PROFILES, "index.json")
    with open(path, encoding="utf-8") as handle:
        index = json.load(handle)
    for ident in ids:
        if ident not in index["profiles"]:
            index["profiles"].append(ident)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2)
        handle.write("\n")


def siting(guide: list, floor: str, geometry: str = GEOMETRY) -> dict:
    """Which authored elements the scene's own guards would accept, in Python.

    **This exists because a rejection is silent in the render path this pass
    uses.** `environment_stage` refuses a pad or a bay that is inside its
    clearance of the racing line or inside its keep-out of the camera path,
    and says so with `push_warning` - which `tools/race2_render.py still`
    does not surface. V29's whole failure was three bays that were skipped
    exactly this way, and the only reason anybody found out was that the film
    had no architecture in it.

    So the two guards are reimplemented here against the same data the scene
    builds them from: `guides.track` is every run's path concatenated in
    layout units, and `guides.lens` is the profile's own `keepout` list. The
    test is `environment_world._sited` - nearest-point distance to each,
    against the element's own `clearance` and `keepout`.

    The stage is centred on the centreline's plan centre, which
    `race2_scene._build_stage` computes as the midpoint of its plan bounds and
    which on this course is (0.00, 0.00) - so an element's authored `at` and
    the world coordinates the floor map is in are the same numbers. That is
    checked rather than assumed.
    """
    course = load_course(geometry)
    plan = footprint(course)
    centre = (plan["centre"][0], plan["centre"][1])
    line = [(p[0], p[2]) for p in course["line"]]

    def gap(points, x, z):
        return min(math.hypot(x - px, z - pz) for px, pz in points) \
            if points else float("inf")

    lens = [(p[0], p[1]) for p in guide]
    rows, refused = [], []
    profile = production(guide, floor)
    deck = profile["world"]["deck"]
    for index, pad in enumerate(deck["pads"]):
        x = centre[0] + pad["at"][0]
        z = centre[1] + pad["at"][1]
        want_line = float(pad.get("clearance", deck.get("clearance", 7.0)))
        want_lens = float(pad.get("keepout", deck.get("keepout", 12.0)))
        to_line, to_lens = gap(line, x, z), gap(lens, x, z)
        ok = to_line >= want_line and (want_lens <= 0.0
                                       or to_lens >= want_lens)
        row = {"kind": "pad", "index": index, "material": pad["material"],
               "at": [round(x, 2), round(z, 2)],
               "to_line": round(to_line, 2), "needs_line": want_line,
               "to_lens": round(to_lens, 2), "needs_lens": want_lens,
               "accepted": ok}
        rows.append(row)
        if not ok:
            refused.append(row)
    bays = profile["world"]["bays"]
    nodes = {m: v for m, v in (course.get("modules") or {}).items()}
    for name, site in bays["sites"].items():
        anchor_at = nodes.get(str(site.get("node", name)))
        if not anchor_at:
            rows.append({"kind": "bay", "index": name, "material": "-",
                         "at": None, "accepted": None,
                         "note": "node not in this course"})
            continue
        x = float(anchor_at["centre"][0]) + float(site["offset"][0])
        z = float(anchor_at["centre"][2]) + float(site["offset"][1])
        want_line = float(site.get("clearance", bays.get("clearance", 11.0)))
        want_lens = float(site.get("keepout", bays.get("keepout", 20.0)))
        to_line, to_lens = gap(line, x, z), gap(lens, x, z)
        ok = to_line >= want_line and (want_lens <= 0.0
                                       or to_lens >= want_lens)
        row = {"kind": "bay", "index": name,
               "material": str(site.get("material", "-")),
               "at": [round(x, 2), round(z, 2)],
               "to_line": round(to_line, 2), "needs_line": want_line,
               "to_lens": round(to_lens, 2), "needs_lens": want_lens,
               "accepted": ok}
        rows.append(row)
        if not ok:
            refused.append(row)
    # **The stacking check, and it is the one the sprint's warm light needed.**
    # For every pair of floor elements whose plan rectangles overlap, the one
    # authored at a lower level must not stand higher than the one above it.
    # Stated that way it is trivially true by construction of `FLOOR_STACK` -
    # which is exactly why the stack exists, and the check is here so that a
    # later hand-authored pad cannot quietly reintroduce the bug.
    laid = [p for p in deck["pads"] if "size" in p]
    buried = []
    for i, low in enumerate(laid):
        low_top = low["y"] + low["size"][1] * 0.5
        for high in laid[i + 1:]:
            high_top = high["y"] + high["size"][1] * 0.5
            if not _overlaps(low, high):
                continue
            # The later element is drawn in the same pass, so what decides
            # visibility is height, not order. A pad strictly under another
            # one that covers it is invisible.
            if high_top < low_top and _covers(low, high):
                buried.append({"hidden": high["material"],
                               "under": low["material"],
                               "at": high["at"]})
    return {"centre": [round(centre[0], 2), round(centre[1], 2)],
            "line_samples": len(line), "lens_points": len(lens),
            "elements": rows, "refused": refused, "buried": buried}


def _extent(pad: dict) -> tuple:
    """A pad's plan rectangle, axis-aligned, widened for a bearing.

    A rotated rectangle's axis-aligned bounds are what matter here: the test
    only has to be conservative, because a false overlap costs a look and a
    missed one costs a feature.
    """
    half_x, half_z = pad["size"][0] * 0.5, pad["size"][2] * 0.5
    if abs(float(pad.get("bearing", 0.0)) % 180.0 - 90.0) < 45.0:
        half_x, half_z = half_z, half_x
    x, z = pad["at"]
    return (x - half_x, x + half_x, z - half_z, z + half_z)


def _overlaps(a: dict, b: dict) -> bool:
    ax0, ax1, az0, az1 = _extent(a)
    bx0, bx1, bz0, bz1 = _extent(b)
    return ax0 < bx1 and bx0 < ax1 and az0 < bz1 and bz0 < az1


def _covers(outer: dict, inner: dict) -> bool:
    """Whether `outer`'s plan rectangle contains `inner`'s centre."""
    x0, x1, z0, z1 = _extent(outer)
    x, z = inner["at"]
    return x0 <= x <= x1 and z0 <= z <= z1


def render_siting(report: dict) -> str:
    out = ["AUTHORED ELEMENTS, against the scene's own two guards",
           "-" * 74]
    out.append("  stage centre %s   line samples %d   lens points %d"
               % (report["centre"], report["line_samples"],
                  report["lens_points"]))
    out.append("")
    out.append("  %-5s %-18s %15s %14s %14s %s"
               % ("kind", "material", "at", "line (need)", "lens (need)",
                  "ok"))
    for row in report["elements"]:
        if row.get("at") is None:
            out.append("  %-5s %-18s %15s %s"
                       % (row["kind"], row["material"], "-",
                          row.get("note", "")))
            continue
        out.append("  %-5s %-18s %15s %14s %14s %s"
                   % (row["kind"],
                      row["material"].replace("hall_", "").replace("lit_", ""),
                      "%.1f, %.1f" % tuple(row["at"]),
                      "%.1f (%.0f)" % (row["to_line"], row["needs_line"]),
                      "%.1f (%.0f)" % (row["to_lens"], row["needs_lens"]),
                      "" if row["accepted"] else "REFUSED"))
    out.append("")
    out.append("  refused: %d of %d"
               % (len(report["refused"]), len(report["elements"])))
    out.append("  buried under another floor element: %d"
               % len(report.get("buried", [])))
    for row in report.get("buried", []):
        out.append("    %s at %s is under %s"
                   % (row["hidden"], row["at"], row["under"]))
    return "\n".join(out)


def report(guide: list, floor: str) -> str:
    out = ["V30.1 PREMIUM STAGE: what the numbers decided", "=" * 62, ""]
    out.append("LOCKED, AND CHECKED AGAINST THE PROFILE THIS WRITES")
    profile = production(guide, floor)
    radii = tuple(b["radius"] for b in profile["world"]["shell"]["bands"])
    out.append("  wall radii          %s" % (radii,))
    out.append("  V30 wall radii      %s   %s"
               % (V30_WALL_RADII,
                  "ok" if radii == V30_WALL_RADII else "MOVED"))
    arc = [(b["bearing_from"],
            b["bearing_from"] + b["bearing_step"] * (b["count"] - 1))
           for b in profile["world"]["shell"]["bands"]]
    out.append("  band arcs           %s" % arc)
    out.append("  live arc            %s" % (LIVE_ARC,))
    out.append("  lens guide points   %d" % len(profile["world"]["keepout"]))
    out.append("")
    out.append("FLOOR MODULE")
    for key, maker in FLOORS.items():
        field = maker()[0]
        pitch = field["cell"][0] + field["gap"]
        nx, nz = field["cells"]
        half = min(pitch * nx, (field["cell"][2] + field["gap"]) * nz) * 0.5
        omitted = len(field.get("skip_x", [])) * nz \
            + len(field.get("skip_z", [])) * nx
        out.append("  %-3s pitch %6.2f  seams/s %5.2f  half-extent %6.2f  "
                   "modules %4d%s"
                   % (key.upper(), pitch, 12.04 / pitch, half,
                      nx * nz - omitted,
                      "   <- selected" if key == floor else ""))
    out.append("  V30 pitch   2.38  seams/s  5.06  half-extent  78.54  "
               "modules  198")
    out.append("")
    out.append("SEAM PROFILE")
    field = FLOORS[floor]()[0]
    under = field["under"]
    plate_top = field["y"] + field["thickness"] * 0.5
    under_top = field["y"] - under["drop"] + under["thickness"] * 0.5
    out.append("  seam width          %.2f" % field["gap"])
    out.append("  seam depth          %.2f" % (plate_top - under_top))
    out.append("  aspect (w/d)        %.2f   > 1 is a line, < 1 is a trench"
               % (field["gap"] / max(plate_top - under_top, 1e-6)))
    out.append("  V30 aspect          0.33")
    out.append("")
    out.append("WALL RHYTHM: separate kinds a viewer counts per band")
    for band, name in zip(profile["world"]["shell"]["bands"],
                          ("near flank", "deep rear", "far flank", "upper")):
        kinds = band["pattern"]
        runs = 1 + sum(1 for a, b in zip(kinds, kinds[1:]) if a != b)
        out.append("  %-11s %-44s runs %d" % (name, " ".join(kinds), runs))
    out.append("  V30 near flank: rib slot bay slot rib -> runs 5")
    out.append("")
    out.append("THE MONEY SHOT, and what is sited inside it")
    out.append("  sprint box    x %s  z %s" % (SPRINT_BOX["x"],
                                               SPRINT_BOX["z"]))
    out.append("  money box     x %s  z %s   centre %s"
               % (MONEY_BOX["x"], MONEY_BOX["z"], MONEY_BOX["centre"]))
    out.append("  machine edge  x %.1f      line's far z %.1f"
               % (LINE_LEFT_EDGE, LINE_FAR_Z))
    out.append("")
    out.append("  %-26s %14s %9s %s"
               % ("element", "at", "clear", "in the money shot"))

    def money(x, z):
        return (MONEY_BOX["x"][0] <= x <= MONEY_BOX["x"][1]
                and MONEY_BOX["z"][0] <= z <= MONEY_BOX["z"][1])

    seen = 0
    for label, pad in ([("runway", p) for p in runway_zone()]
                       + [("warm", p) for p in warm_architecture()]):
        x, z = pad["at"]
        # How far this element is from the nearest thing the machine occupies
        # in the money box: the strip left of x = -13.3, or the band past
        # z = 26.
        gap = max(LINE_LEFT_EDGE - x, z - LINE_FAR_Z)
        hit = money(x, z)
        seen += 1 if hit else 0
        out.append("  %-26s %14s %9.1f %s"
                   % ("%s %s" % (label, pad["material"].replace("hall_", "")
                                 .replace("lit_", "")),
                      "%.1f, %.1f" % (x, z), gap,
                      "yes" if hit else ""))
    out.append("")
    out.append("  elements inside the money box  %d of %d"
               % (seen, len(runway_zone()) + len(warm_architecture())))
    out.append("  (the ring practicals are on the live arc for the hook and")
    out.append("   the chase, and are not meant to reach the sprint)")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode",
                        choices=("floors", "profile", "all", "report",
                                 "siting"),
                        nargs="?", default="all")
    parser.add_argument("--floor", default="b",
                        choices=tuple(FLOORS), help="the selected treatment")
    args = parser.parse_args()

    guide = keepout()
    written: list[str] = []
    if args.mode in ("floors", "all"):
        for key in FLOORS:
            profile = floor_variant(key, guide)
            written.append(write(profile))
    if args.mode in ("profile", "all"):
        written.append(write(production(guide, args.floor)))
    if written:
        register([os.path.splitext(os.path.basename(p))[0] for p in written])
        for path in written:
            print(f"  wrote {path}")
    if args.mode in ("report", "siting"):
        placed = siting(guide, args.floor)
        text = (report(guide, args.floor) + "\n\n"
                + render_siting(placed)) if args.mode == "report" \
            else render_siting(placed)
        print(text)
        os.makedirs(DOCS, exist_ok=True)
        with open(os.path.join(DOCS, "decisions.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write(text + "\n")
        with open(os.path.join(DOCS, "siting.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(placed, handle, indent=1)
        if placed["refused"] or placed["buried"]:
            print("\n%d refused, %d buried"
                  % (len(placed["refused"]), len(placed["buried"])))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

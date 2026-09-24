"""Category 3, Test #2 - the TWO-TEAM composition contract, Phase 4A.

This module is a **playback consumer and nothing else**. It reads the canonical
V3 document written by `satisfying.multishell_playback` and turns it into the
numbers a renderer needs: where the camera is, how big a thing is in pixels,
which of two colours a ball wears, which of the five damage states a panel is
in. It never imports `satisfying.multishell`, never integrates, never resolves
a contact, and never touches a seed. The one rule the document states -

    a consumer of this document may read a trajectory and may not compute one

- is the reason this file exists at the same time as `multishell_scene.gd`:
every constant the scene draws with is declared here, a test parses the
GDScript and compares the two, and a measurement printed in the report is
therefore a measurement of the render that was actually made.

## The frustum, and why that sentence was not true until Phase 4A

It was not. From Phase 2A until Phase 4A, `CAMERA_FRUSTUM_SIZE` was the near
plane's *height* while `Camera3D.keep_aspect = KEEP_WIDTH` made Godot read it
as the near plane's *width*. The horizontal field was therefore 74.4 degrees
rather than the declared 47, every framing was 1.778x wider than this module
computed, and the arena filled **46.9% of the frame where the report said
83.4%**. Every pixel figure in the Phase 2A, Phase 3 and Phase 3B evidence -
ball diameter, wall thickness, opening width, the 18.4 px action-rail clearance
- described a render nobody made.

It survived three phases because the only test on the constant compared the
Python copy with the GDScript copy, and both copies were wrong in the same way.
Two files agreeing is not a measurement. `test_the_frustum_matches_the_declared_field_of_view`
re-derives the half-angle from Godot's own frustum arithmetic instead, which is
the check that would have caught it on the day.

It also explains the Phase 3B human review. "The arena becomes too small
relative to the vertical frame" and "too much empty dark space appears
precisely when action should be increasing" are exactly what a camera 1.778x
too wide looks like, and no amount of retuning `VIEW_DIAMETER_FRACTION` could
have fixed it, because that number was not the one the renderer used.

## The Phase 4A camera, in four decisions

**Centred.** `ARENA_CENTRE_X_FRACTION` was 0.420. Sliding the arena 8% of the
frame left bought a disc 22% wider and the review's first finding is that the
result looks off-centre - which it is, by 86 px at 1080. The arena is now on
the frame's own vertical axis and the width is whatever that allows: the
conservative action rail begins at x = 0.840, so the frontier gets 0.652 of the
frame width and clears the rail by 15.1 px. The only asymmetry left is
vertical, and it is the midpoint of the band the player's furniture leaves
visible.

**Constant frontier size.** The framed radius is the frontier's material edge
times a fixed fraction, not plus a fixed number of world units. A constant pad
is a shrinking *fraction* as the arena opens out - 14% of the framing at the
innermost shell and 3.5% at the outermost - so the Phase 3B frontier crept from
73% to 81% of the frame and the schedule was never actually constant. The
proportional pad makes `frontier_occupancy_report` return the same number at
every stage, exactly, with nothing fitted.

**Less zoom.** The total zoom-out is now a property of the arena rather than of
the camera: under a proportional pad it is the outermost material edge over the
innermost, so the only way to change it is to change the shells. Phase 1 shrank
the arena from an outer radius of 24.4 to 18.5 for this reason, and the ratio
fell from 3.63x to 2.80x. A ball is 73 px across at the opening and still 26 px
at the final wall, where Phase 3B's own arithmetic said 21 px and its renders
actually gave 12.

**Gradual revelation.** At t = 0 the camera frames shell 0 and the outer shells
run off the top and bottom of the frame; each time the canonical high-water
frontier advances a region it opens out one shell. The schedule is a pure
function of the document - `frame_marks` reads the `shell_exit` stream and
nothing else - it is monotone by construction, and it is the escalation: the
world the viewer is looking at gets bigger because the balls got further.

## Two colours, and what had to move out of their way

A ball's hue is its team's hue, exactly, for every generation. Phase 3B gave
each founder-child its own family hue and paled each generation toward white;
both are gone, because the video's question is "which colour gets out first"
and a fourth-generation cyan paled 45% toward white stops answering it.
Generation reads as emission only.

Taking the warm end of the spectrum for a team cost the arena its damage
palette. Phase 3B reserved amber-to-red for damage on the argument that a
viewer should never have to ask whether an orange thing is a ball or a wound;
that argument is now paid for by moving the damage ramp to crimson-to-hot-white
and the opening-post highlight from cyan to steel.
`test_no_damage_or_structure_colour_can_be_mistaken_for_a_team` measures the
separation rather than asserting it - which is how the first replacement ramp,
a red that sat 0.354 from orange, was caught.

## Depth, and why the camera is perspective

A wall 0.30 units thick is 5.7 px at the final framing. Nothing drawn inside
the canonical silhouette can be made to look massive at 5.7 px, so the mass
comes from **behind** it: each panel is extruded backwards, away from the
camera, and a perspective camera sees the receding flank. A point at `z = -d`
and radius `r` projects to radius `r*D/(D+d)`, which is *inside* the panel's
front face, so a flank never covers a ball - every ball is at `z = 0`, in front
of every flank. `PANEL_DEPTH` was re-spread for the smaller arena, because a
flank is `r*d/(D+d)` and the old ramp lost most of its spread with the radius:
the outermost wall now measures 23.8 px against the innermost's 7.0.

Everything the physics cares about is at `z = 0`, and a perspective camera
looking down `-Z` projects that plane by an exact uniform scale. The eye stays
on the invariant world origin and an asymmetric frustum places the principal
point; a laterally translated eye would give the five slabs depth-dependent
parallax and make their rear rims appear to have different centres.

## The candidate set

414 seeds of the 20,000-seed population pass the engineering rule.
`CANDIDATE_SEEDS` names the six rendered for human review and says why each one
is there; `CANDIDATE_RULE` is the gate they all clear. Nothing in either
mentions the finishing margin or the lead-change count, because a rule that
rewarded a narrow finish would be, one sweep later, a rule that selects for
arranged ones.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
from typing import Any, Mapping, Sequence

from satisfying.multishell_playback import panel_state_at, position_at
from satisfying.tile_safe_area import DEFAULT_SAFE_AREA, Region, SafeAreaConfig

__all__ = [
    "EXPECTED_SCHEMA_VERSION",
    "EXPECTED_CONFIG_DIGEST",
    "FRAME_WIDTH",
    "FRAME_HEIGHT",
    "VIEW_DIAMETER_FRACTION",
    "ARENA_CENTRE_X_FRACTION",
    "ARENA_CENTRE_Y_FRACTION",
    "VIEW_PAD_FRACTION",
    "FRONTIER_WIDTH_FRACTION",
    "USABLE_WIDTH_FRACTION",
    "TEAM_RGB",
    "TEAM_NAMES",
    "CAMERA_HFOV_DEGREES",
    "CAMERA_NEAR",
    "CAMERA_FRUSTUM_SIZE",
    "CAMERA_FRUSTUM_OFFSET",
    "FRAME_LEAD_SECONDS",
    "FRAME_EASE_SECONDS",
    "BALL_DRAW_SCALE",
    "HALO_SCALE",
    "BALL_RIM_SCALE",
    "TRAIL_SECONDS",
    "TRAIL_SAMPLES",
    "PANEL_DEPTH",
    "POST_DEPTH_FACTOR",
    "PANEL_CHAMFER",
    "DAMAGE_STATES",
    "CANDIDATE_RULE",
    "CANDIDATE_SEEDS",
    "validate_document",
    "frame_marks",
    "view_radius_at",
    "pixels_per_unit",
    "camera_distance",
    "flank_width",
    "project",
    "project_3d",
    "projected_shell_centres",
    "centre_alignment_report",
    "alignment_moments",
    "shell_material_radii",
    "zoom_ratio",
    "frontier_occupancy_report",
    "centring_report",
    "team_palette",
    "team_of",
    "team_population_at",
    "shell_geometry_report",
    "composition_report",
    "safe_area_report",
    "readability_report",
    "damage_report",
    "wound_seams",
    "panel_damage_teams",
    "panel_roughness",
    "critical_visibility_report",
    "containment_report",
    "event_moments",
    "measure_document",
    "candidate_seeds",
    "candidate_manifest",
    "render_config",
    "render_config_digest",
]

# --------------------------------------------------------------------------
# What this consumer will read, and refuses to read
# --------------------------------------------------------------------------

EXPECTED_SCHEMA_VERSION = "category3-test2-two-team-shell-race/3.0.0"
# The frozen Phase 1 operating configuration. A document from any other config
# renders a plausible video of a different simulation, which is worse than an
# error, so this is checked rather than trusted.
EXPECTED_CONFIG_DIGEST = (
    "4a3ab8ba22ae7c54981700823cc5b4eaf147c72fc5ab609a244d9cbaeb6ce572"
)
EXPECTED_SHELL_COUNT = 5

DAMAGE_STATES: tuple[str, ...] = (
    "healthy", "damaged", "critical", "fractured", "broken",
)

# --------------------------------------------------------------------------
# Frame and composition
# --------------------------------------------------------------------------

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

# --- the Phase 4A camera --------------------------------------------------
#
# Three things changed and each one answers a specific line of the human review.
#
# **Centred.** `ARENA_CENTRE_X_FRACTION` was 0.420. Sliding the arena 8% of the
# frame to the left bought a disc 22% wider, and the review's first finding is
# that the result looks off-centre - which it is, by 86 px at 1080. The arena is
# now on the frame's own vertical axis and the width is whatever that allows.
ARENA_CENTRE_X_FRACTION = 0.500
# The Shorts furniture is not symmetric top to bottom: the top bar takes 6% and
# the title block, scrubber and nav row take the bottom 16%, so the midpoint of
# the band a viewer actually sees is 0.450, not 0.500. This is the *only*
# asymmetry left in the composition and it is vertical, where nothing about the
# arena's shape makes it read as a slide.
ARENA_CENTRE_Y_FRACTION = 0.450
# **Constant frontier size.** The framed radius is the frontier shell's own
# material edge scaled by a fixed fraction, not its material edge plus a fixed
# number of world units. A constant pad is a *shrinking* fraction as the arena
# opens out - 14% of the framing at the innermost shell and 3.5% at the
# outermost under Phase 3B - so the frontier crept from 73% to 81% of the frame
# and the schedule was never actually constant. A proportional pad makes the
# frontier occupy the same fraction of the frame at every stage, by
# construction, which is what "constant frontier screen size" has to mean if it
# is to be checkable.
VIEW_PAD_FRACTION = 0.055
# **How big the important play region is.**  The framed shell's outer material
# diameter as a fraction of the frame width.
#
# Phase 4A derived 0.652 from "fit the whole arena inside the band that clears
# the Shorts action rail". Phase 4B overturned that rule and reached 0.850 -
# still a rule that fits the whole arena inside the *frame*, just a different
# rectangle. The human review rejected 4B for the same reason it rejected 4A:
# the race is too small and there is too much empty dark space.
#
# 4C drops the last of it. The rule is now *keep the interesting action large,
# even if parts of the arena are cropped*, so the constant is allowed above
# 1.0, where the framed shell's material diameter is **wider than the frame**
# and its left and right caps are off screen. The brief named three widths for
# the final structure - 100%, 110% and 120% of the frame - and they were
# rendered on seed 17964 and compared as frames
# (`tools/two_team_phase4c_lab.py framing`), with the 4B fraction carried as
# the "what we had" control at the 4C stage plan:
#
#   | variant | mean ink | early | late | worst empty band | ball | opening | wall |
#   |---|---:|---:|---:|---:|---:|---:|---:|
#   | 4B 0.850 | 0.456 | 0.504 | 0.402 | 531 px | 33.9 | 35.9 | 57.2 |
#   | A 1.000  | 0.531 | 0.560 | 0.508 | 479 px | 39.9 | 42.3 | 76.3 |
#   | B 1.100  | 0.566 | 0.580 | 0.564 | 431 px | 43.9 | 46.5 | 90.4 |
#   | C 1.200  | 0.590 | 0.590 | **0.607** | **382 px** | **47.9** | **50.7** | **105.4** |
#
# **C is the only variant whose late frame is not emptier than its opening** -
# 0.607 against 0.590 measured off the pixels on 17964, and 0.648 against
# 0.590 on 1176 - which is the one item the 4B phase could not deliver at all.
# It is also monotone in every other column, so there is no trade inside the
# brief's band: C is simply the far end of it.
#
# What C costs, stated rather than hidden:
#
#   * 7 of 17964's 78 ordinary frontier crossings and 3 of its near misses end
#     up partly under the action rail or off the frame edge. **Every hard class
#     - the first clone, every break some ball later used as a passage, and the
#     winning escape - is fully visible at 1.00, 1.10 and 1.20 alike on both
#     production candidates.**
#   * a ball is partly off frame on 8.5% of 17964's frames and 11.6% of
#     1176's, always at the horizontal caps of the outer region, never before
#     the camera locks.
#   * the escapee's *run-on* past the arena leaves the frame sooner. On 17964
#     it is fully framed for 0.05 s of the 0.55 s release at C against 0.47 s
#     at A; on 1176 it is framed for the whole release at every fraction,
#     because its escape is at the bottom-left rather than at a cap. That is
#     one of the reasons 1176 is the production candidate.
#
# `critical_visibility_report` measures the action rail *and* the frame edge,
# because above 1.0 the edge is the binding one.
FRONTIER_WIDTH_FRACTION = 1.200
# What is left after the player's own controls, as the brief's "usable screen
# width": the widest horizontally centred band that clears the action rail.
# Stated here so the occupancy report can quote the frontier against both this
# and the raw frame width rather than leaving the reader to guess which one a
# percentage means.
USABLE_WIDTH_FRACTION = 2.0 * (0.840 - ARENA_CENTRE_X_FRACTION)
# The framed disc, pad included, as a fraction of the frame width.
VIEW_DIAMETER_FRACTION = FRONTIER_WIDTH_FRACTION * (1.0 + VIEW_PAD_FRACTION)
# Kept for readers of the old constant: at the final framing the proportional
# pad is worth this many world units. Nothing reads it.
VIEW_RADIUS_PAD = None

# Horizontal field of view. `Camera3D.keep_aspect = KEEP_WIDTH` makes `fov` the
# horizontal angle, so this and VIEW_DIAMETER_FRACTION together fix the camera
# distance at every framing - see `camera_distance`. 47 degrees puts the
# outermost shell 19.2 degrees off axis at the final framing, which is what
# makes its 3.2-unit flank 18.9 px wide.
CAMERA_HFOV_DEGREES = 47.0
CAMERA_NEAR = 0.20
# An asymmetric perspective frustum keeps the camera itself on the canonical
# world centre.  The offset moves the principal point to the Shorts-safe
# composition point without introducing the depth-dependent parallax caused by
# translating the camera laterally.
#
# **This constant was wrong from Phase 2A until Phase 4A and the error was
# 1.778x.** `Camera3D.keep_aspect = KEEP_WIDTH` makes Godot read the frustum
# `size` as the near plane's *width*:
#
#     left/right  = -+ size / 2            + offset.x
#     top/bottom  = -+ size / aspect / 2   + offset.y      (aspect = W / H)
#
# so `size` is `2 * near * tan(hfov / 2)` and the height follows from the
# aspect. The old constant multiplied that by `FRAME_HEIGHT / FRAME_WIDTH`,
# which set the near width to the near *height* and opened the horizontal field
# from 47 to 74.4 degrees. Every pixel figure this module reported therefore
# described a render nobody made: `VIEW_DIAMETER_FRACTION` said the framed disc
# filled 83.4% of the frame and it actually filled 46.9%, and the outermost
# shell sat 250 px clear of the action rail rather than the 18.4 px the
# safe-area report claimed.
#
# It also explains the human review directly. "The arena becomes too small
# relative to the vertical frame" and "too much empty dark space appears
# precisely when action should be increasing" are what a 1.778x over-wide
# camera looks like, and no amount of retuning `VIEW_DIAMETER_FRACTION` would
# have fixed it, because the number was not the one the renderer used.
#
# `test_the_frustum_matches_the_declared_field_of_view` is the check that would
# have caught it: it re-derives the horizontal half-angle from the constant and
# from Godot's own frustum arithmetic, rather than comparing two copies of the
# same wrong number.
CAMERA_FRUSTUM_SIZE = 2.0 * CAMERA_NEAR * math.tan(math.radians(CAMERA_HFOV_DEGREES) * 0.5)
# The offsets are expressed against the near plane's own width and height, so
# each one moves the principal point by its fraction of the frame. With the
# arena now on the frame's axis the horizontal offset is exactly zero.
CAMERA_FRUSTUM_OFFSET = (
    (0.5 - ARENA_CENTRE_X_FRACTION) * CAMERA_FRUSTUM_SIZE,
    (ARENA_CENTRE_Y_FRACTION - 0.5)
    * CAMERA_FRUSTUM_SIZE
    * FRAME_HEIGHT
    / FRAME_WIDTH,
)

# --- the Phase 4C camera schedule ----------------------------------------
#
# `(trigger_region, extent_shell)`, outward. The camera holds `extent_shell`'s
# material edge at FRONTIER_WIDTH_FRACTION of the frame until the canonical
# high-water frontier reaches `trigger_region`, and then eases out to the next
# stage. Stage 0 has no trigger and is the opening framing.
#
# **One transition, and the grouping is again forced rather than chosen.**
# Phase 4A moved four times, 4B twice, and the review asks for at most one. The
# brief adds a requirement 4B did not have - the final 6 to 10 seconds must be
# fully static - and that is what picks the pair:
#
#   1. the last stage's extent is shell 4, because the final wall has to be
#      framed when the winner leaves through it;
#   2. no ball may be outside the frame *before* the move, so the opening
#      extent must cover every region the race reaches first;
#   3. the move must leave at least 6 s of locked camera, which rules out
#      triggering on region 4: that arrives 4.47 s and 5.52 s before the escape
#      on the two production candidates, and 4B's static tails were 4.16 s and
#      5.21 s for exactly this reason.
#
# Triggering on region 2 - the frontier crossing shell 1 - is the latest
# trigger that clears rule 3 on both candidates with room to spare (20.79 s and
# 11.46 s of static tail) and it is late enough to be *meaningful*: the race
# has left the two inner shells and is into the second half of the arena.
# Rule 2 then wants the opening to cover regions 0 and 1, whose material edge
# is shell 1's at 9.65 units; extent shell 2 frames 12.65 units, which contains
# it with the drawn ball at every fraction the experiment tested and is the
# tightest opening that does.
#
# The pleasant arithmetic: both stages divide by the same fraction, so the
# single zoom is 12.65 -> 18.65 = **1.474x whatever the fraction is**, against
# 4B's 1.62x first step and 1.933x total. One move, and a smaller one.
CAMERA_STAGE_PLAN: tuple[tuple[int, int], ...] = ((0, 2), (2, 4))

# The framing opens this long before the canonical crossing that triggers it,
# so the frame is already moving as the ball goes through rather than reacting
# after it.
FRAME_LEAD_SECONDS = 0.14
# The brief's band is 0.25-0.40 s in 4C, down from 4B's 0.25-0.45, and there is
# now only one payment to make.
#
# A zoom's cost to the viewer is the screen velocity it induces: a world point
# at the frame edge slides inward while the framed radius grows, and that
# velocity is the step divided by the duration. The gate is unchanged from 4B -
# `CAMERA_VELOCITY_HEADROOM`, twice the fastest a ball ever crosses the opening
# framing - and it is **not** slack here, because the 4C opening frames shell 2
# rather than shell 1, so the ball's own reference screen velocity is a third
# smaller and the same move costs more against it. Measured on both production
# candidates at 60 fps:
#
#     0.25 s -> 3.07x    0.30 s -> 2.57x    0.35 s -> 2.20x    0.40 s -> 1.93x
#
# 0.40 s is the slowest the brief allows and the **only** value in the band
# that passes the 2.0x gate, so it is not a preference: every faster value in
# the band makes the one remaining move more noticeable than either of 4B's
# two, and the gate says so rather than my taste saying so.
FRAME_EASE_SECONDS = 0.40

# --- event protection ------------------------------------------------------
#
# A zoom may not run across a moment the viewer is supposed to be watching. The
# protected instants are canonical: the first clone, every panel break, every
# strong near miss, and the escape. If the motion window would contain one, the
# transition is pushed to just after it and re-checked.
#
# The deferral is bounded, because an unbounded one could push a transition
# past the event it exists to frame. Measured on the three review candidates
# the cap is never reached: the deferrals are 0.00, 0.52, 0.77, 0.00, 0.00 and
# 0.00 seconds, against a cap of 0.90.
EVENT_GUARD_BEFORE_SECONDS = 0.12
EVENT_GUARD_AFTER_SECONDS = 0.22
EVENT_GUARD_MAX_DEFER_SECONDS = 0.90
#: A near miss closer than this many ball radii is worth protecting.
STRONG_NEAR_MISS_RADII = 0.75

# --------------------------------------------------------------------------
# Balls
# --------------------------------------------------------------------------

# A ball touching a panel has its centre `ball_radius + 0.15` units from the
# chord axis, so `(0.53 + 0.15) / 0.53 = 1.283` is the largest scale that never
# draws the ball inside a panel it is only touching. 1.30 overlaps by 0.009
# units - 0.5 px at the opening framing, 0.2 px at the final one - which is
# below the bloom's own falloff and reads as contact rather than penetration.
# It is down from Phase 3B's 1.50 only because the ball itself grew from 0.40
# to 0.53; the drawn ball is larger in world units and much larger on screen.
BALL_DRAW_SCALE = 1.30
# The additive halo billboard, as a multiple of the drawn core radius. Down from
# 2.60: with two saturated team colours and fifteen to thirty balls late on, a
# wide additive halo is exactly the mechanism that turns a crowd into one white
# blob, and the blob would destroy the one thing this redesign must protect -
# which colour is which.
# Down again for 4B. Bloom is a world-unit radius, so it scales with the ball
# on screen and the white-out risk is unchanged by the framing - but the frame
# now holds the late population at a size where overlapping halos are actually
# read, rather than being a 26 px smudge. 1.90 keeps the additive glow inside
# the drawn rim at the final framing, which is what stops a cyan knot and an
# orange knot both resolving to white.
HALO_SCALE = 1.90
# A near-black disc behind each core, slightly larger than it, drawn at a small
# negative z so a core always wins the depth test against another ball's rim.
# Seven balls inside two drawn diameters happens - seed 7183 at 15.6 s - and
# seven overlapping bright discs with no rims are one blob, while seven with
# rims are still seven.
BALL_RIM_SCALE = 1.24
# The presentation layers sit just *in front* of the play plane so they read
# over a panel instead of being occluded by one. The core sphere - the
# canonical position - is at z = 0 exactly.
BALL_RIM_Z = 0.02
TRAIL_Z = 0.06
HALO_Z = 0.12
EFFECT_Z = 0.16
# A time window, not a frame count, so the trail is identical at any rate. At
# 10 units/s the ball moves about half its own drawn diameter per frame at
# 30 fps, so - unlike Test #1 - it never strobes and the trail is not needed
# for continuity at all. It is here for two other jobs: it says which ball is
# which inside a knot, and it is what turns a pile of seven balls into seven
# diverging streaks.
#
# **Shortened for 4B.** The trail is a length in world units, so raising the
# frame fraction from 0.652 to 0.850 made every streak 30% longer on screen
# without a constant changing. At eighteen balls that is the "spaghetti"
# the brief warns about, and the brief is explicit that team identification
# beats motion streaks. At the constant speed of 10, 0.16 s was 30.2 px at
# Phase 4A's final framing against a 26.0 px drawn ball - the streak was the
# bigger mark. 0.115 s is 28.3 px at 4B's against a 33.9 px ball, so the ball
# is now the bigger mark and the vector is a hint rather than a ribbon.
TRAIL_SECONDS = 0.115
TRAIL_SAMPLES = 20
TRAIL_HEAD_WIDTH = 0.78
TRAIL_TAIL_WIDTH = 0.24

# --------------------------------------------------------------------------
# Walls
# --------------------------------------------------------------------------

# Backward extrusion per shell, inner to outer. The whole "the outer wall is
# the hardest" read lives in this ramp: nothing else about a panel may grow,
# because the front face is the canonical collision silhouette.
# Re-spread for the smaller Phase 4A arena. The outer radius fell from 24.4 to
# 18.5 and a flank is `r * d / (D + d)`, so the old ramp lost most of its
# spread with the radius: the outermost wall came out 2.99 times the innermost
# where Phase 3B measured 3.6. 0.70 to 3.60 restores it to 3.4 and makes the
# final wall the heaviest object in the frame again.
#
# **Re-spread again for 4B, and this is the whole of "the final wall must feel
# massive".** The brief forbids faking thicker collision geometry, so the front
# silhouette at z = 0 is untouched on every shell and every extra gram of the
# final wall comes from behind it. Three things compound:
#
#   * the ramp itself goes 0.70 -> 6.20 rather than 0.70 -> 3.60;
#   * the larger frame fraction brings the camera in from 65.8 to 50.5 world
#     units at the final framing, and a flank is `r * d / (D + d)`, so the same
#     depth already buys 30% more flank;
#   * the outer shells get a heavier chamfer and a brighter back rim below.
#
# Measured at each phase's own final framing, face plus flank, in 1080-wide
# pixels: Phase 4A ran 6.96 / 8.74 / 11.78 / 16.58 / 23.78 and 4B runs
# 9.57 / 13.04 / 19.96 / 32.79 / 57.20. The final wall is 2.41 times as thick
# as it was, and it is 5.98 times the innermost shell where 4A managed 3.42 -
# and that ramp is the thing a viewer reads as "these get harder".
# `test_the_wall_depth_ramp_is_what_the_report_says` recomputes all ten numbers
# from the frustum rather than comparing two copies of one constant.
PANEL_DEPTH: tuple[float, ...] = (0.70, 1.25, 2.15, 3.60, 6.20)
# Pillars at the shell vertices are the panels' own round caps, so their radius
# is the canonical half-thickness and only their depth is a drawing choice.
#
# **1.55 was the reason the outer walls looked like a cage, and rendering is
# what found it.** A pillar is a cylinder pointing at the camera; at 1.55 times
# the panel depth the outermost shell's pillars were 9.6 world units long and
# projected as 66 radial spikes reaching inward from the wall. Every frame of
# the first 4B render showed the final wall as a comb you could see through -
# which is the opposite of massive, and it was there in Phase 4A too, hidden by
# a camera half the size.
#
# At 0.55 the pillar ends well inside the panel's own depth and reads as what
# it is: the seam between two blocks. The final wall then reads as a solid
# segmented band, which is the "structural segmentation" the brief asked for.
POST_DEPTH_FACTOR = 0.55
# Per shell now rather than one number. A chamfer is a lit edge running the
# length of the panel, and on the outer walls it is the line that separates the
# front face from the flank - the single cue that says "this is a solid block
# seen slightly from the side" rather than "this is a painted arc".
PANEL_CHAMFER = 0.085
PANEL_CHAMFER_BY_SHELL: tuple[float, ...] = (0.085, 0.085, 0.100, 0.115, 0.135)
# Each panel is drawn as three sub-slabs so that `fractured` can separate them
# and a break can retract them into the two posts. They are flush and share one
# material until the panel fractures.
PANEL_SEGMENTS = 3
# Albedo value and specular response, inner to outer: the outer shells are
# darker and more metallic, which reads as denser material under one key light.
SHELL_ALBEDO_VALUE: tuple[float, ...] = (1.00, 0.97, 0.94, 0.91, 0.88)
SHELL_METALLIC: tuple[float, ...] = (0.05, 0.15, 0.25, 0.35, 0.45)
SHELL_ROUGHNESS: tuple[float, ...] = (0.55, 0.49, 0.43, 0.37, 0.31)

# --------------------------------------------------------------------------
# Events, as presentation
# --------------------------------------------------------------------------

SPAWN_FLASH_SECONDS = 0.30
SPAWN_FLASH_RADIUS = 3.10
SPAWN_LINK_SECONDS = 0.18
NEAR_MISS_SECONDS = 0.16
BREAK_FLASH_SECONDS = 0.16
# **The break, rebuilt.** The human review's complaint is that a break reads as
# a marker disappearing rather than as a wall failing. The old sequence was a
# 0.55 s retraction plus eight identical crimson sparks thrown on hashed
# headings - which is a particle puff, and a particle puff is what "indicator"
# looks like. The new sequence is the one the brief spells out: the crack
# network flashes, the slab breaks into a few substantial chunks, the chunks
# leave fast, and a passage is left open.
#
# Retraction is faster because the passage is the point: at 0.30 s the hole is
# open within nine frames at 30 fps, while the chunks are still in the air.
BREAK_RETRACT_SECONDS = 0.30
#: The stress emphasis that precedes the failure, so the wall is seen to give.
#: 4C lengthens it from 0.10: at 30 fps that was three frames, which is a
#: single bright instant rather than a wall visibly straining.
BREAK_STRESS_SECONDS = 0.14
#: Substantial readable chunks, inside the brief's 3-6. Five is one per
#: sub-slab plus two, which is what makes the count read as "the panel came
#: apart" rather than as a number of particles - and 4C raised it from four
#: because the 4C framing draws the outer wall 90 px thick instead of 57, so
#: each chunk is half again as large and four of them left visible gaps in the
#: slab's own footprint as it went.
BREAK_FRAGMENT_COUNT = 5
BREAK_FRAGMENT_SECONDS = 0.42
#: A fragment is a piece of the panel, so its size is the panel's own geometry:
#: this fraction of the chord long, the canonical thickness radially, and this
#: fraction of the shell's depth behind. Nothing about it is a sprite.
BREAK_FRAGMENT_CHORD_FRACTION = 0.22
BREAK_FRAGMENT_DEPTH_FRACTION = 0.60
#: Outward along the break normal, and along the chord, in world units/second.
BREAK_FRAGMENT_OUT_SPEED = 5.2
BREAK_FRAGMENT_SPIN_DEGREES = 220.0
#: Secondary only. Small, few and short, so they read as grit off the fracture
#: rather than as the event itself.
BREAK_DEBRIS_SECONDS = 0.26
BREAK_DEBRIS_COUNT = 5
BREAK_DEBRIS_SIZE = 0.22
BREAK_DEBRIS_SPEED = 6.0
BREAK_DEBRIS_SPEED_SPREAD = 5.0
BREAK_RING_SECONDS = 0.34
BREAK_RING_RADIUS = 3.40
#: **Flood-through.** If this many balls or more use a freshly opened passage
#: within the window, the passage itself answers - the two flanking pillars
#: brighten and a soft light sits in the gap. No screen shake, no global flash,
#: and not one pixel of ball motion changes.
FLOOD_WINDOW_SECONDS = 1.80
FLOOD_MIN_BALLS = 2
FLOOD_RESPONSE_SECONDS = 0.55
FLOOD_POST_ENERGY = 5.4
ESCAPE_FLARE_SECONDS = 0.60
ESCAPE_RING_SECONDS = 0.75
# The release beat. The document ends at the escape, so only the escapee has a
# canonical flight to continue; every other ball is held at its last canonical
# position rather than extrapolated, because a ball still inside the arena has
# walls in front of it and continuing its flight would draw it through one.
# `--release=0` renders the hard cut instead, and Phase 2A compares the two
# rather than assuming.
RELEASE_SECONDS = 0.55
END_HOLD_SECONDS = 0.40

# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------

BACKGROUND_RGB = (0.020, 0.026, 0.042)
FLOOR_RGB = (0.075, 0.100, 0.165)
# The arena throws light into the 71% of the frame it cannot fill, sized from
# the framing rather than from the arena so it is a halo around shell 0 at the
# opening instead of a wash over the hook.
BACKDROP_Z = -6.0
GLOW_POOL_Z = -4.0
GLOW_POOL_RADII = 2.60
GLOW_POOL_ALPHA = 0.42

# Two teams, two hues, and nothing else in the frame may use either of them.
#
# Phase 3B gave each founder-child its own family hue and reserved the whole
# warm end of the spectrum for damage, on the argument that a viewer should
# never have to ask whether an orange thing is a ball or a wound. The two-team
# rule takes the warm end for a team, so that argument has to be paid for
# somewhere else: the damage ramp below moved from amber to red-to-white-hot,
# and the opening-post highlight moved from cyan to steel. A viewer still never
# has to ask, because nothing warm is a wound any more and nothing cyan is a
# panel.
#
# Cyan at 0.14 red and orange at 0.13 blue are near-complementary and roughly
# matched in luminance, so neither colour wins the eye by being brighter and
# both survive the bloom.
TEAM_RGB: tuple[tuple[float, float, float], ...] = (
    (0.140, 0.880, 1.000),   # team 0, cyan
    (1.000, 0.540, 0.130),   # team 1, orange
)
TEAM_NAMES: tuple[str, ...] = ("cyan", "orange")
# A descendant keeps its team's hue *exactly*. Phase 3B paled each generation
# toward white, which is the one thing this redesign cannot afford: a
# fourth-generation cyan paled 45% toward white is no longer obviously cyan in a
# crowd of thirty, and "which colour is winning" is the whole video. Generation
# reads as emission only, which separates siblings under bloom without touching
# the hue.
GENERATION_WHITEN = 0.0
GENERATION_WHITEN_MAX = 0.0
GENERATION_ENERGY_STEP = 0.09
GENERATION_ENERGY_MAX = 1.36

PANEL_RGB = (0.400, 0.440, 0.500)
# The lit face and the lit back rim. A panel's collision surface is 0.30 units
# thick - 5.3 px at the final framing - so it is emitted rather than merely lit,
# and the back rim at z = -depth turns each panel into a well seen down its own
# axis: two bright lines with the flank between them, and the distance between
# them *is* the depth. That is where "the outer wall is the hardest" comes from.
FACE_RGB = (0.620, 0.680, 0.780)
FACE_ENERGY = 0.62
BACK_RGB = (0.340, 0.430, 0.560)
BACK_ENERGY = 0.30
# A pillar exists only where a panel ends, because a pillar is the panel
# capsule's own round cap. One that flanks an opening is the one a ball clips
# when it aims at the hole and misses, so it carries a cool cap and more depth.
POST_RGB = (0.330, 0.370, 0.440)
# **The pink the human review kept seeing.** A pillar flanking a broken panel
# keeps this cast for the rest of the run - "the arena remembers" - so with 31
# breaks on 17964 the late frame carried up to 62 saturated magenta pillars,
# and the first 4C render made it obvious that *this*, not the wounds, was the
# dominant pink in the picture. It is by construction a coloured dot beside
# every break, which is the definition of the floating marker the brief bans.
#
# It keeps its job and loses its colour: a pale warm cast, the same "this was
# heated and it stayed heated" read as the rest of the 4C damage ramp, still
# 0.71 from team orange and 0.89 from team cyan, and distinguished from the
# cool `POST_EDGE_RGB` cap by being warm rather than by being loud.
POST_HOT_RGB = (1.000, 0.870, 0.760)
# Was cyan, which is now a team. Steel keeps the opening-flanking posts legible
# as structure without borrowing either colour.
POST_EDGE_RGB = (0.700, 0.780, 0.900)
POST_EDGE_ENERGY = 1.60
POST_BASE_ENERGY = 0.26
POST_EDGE_DEPTH = 1.35
# The damage ramp: **exposed material, then heat.**
#
# 4B ran crimson to magenta to pink, which is how it satisfied
# `test_no_damage_or_structure_colour_can_be_mistaken_for_a_team` - pushing
# toward magenta buys back the blue channel team orange does not have. The
# human review then said the result "still reads too much like red/pink marks
# rather than physical destruction", and it was right: a saturated magenta
# hairline is a colour nothing in a wall has, so the eye reads it as a symbol
# drawn on the wall rather than as the wall failing.
#
# 4C keeps the separation requirement and satisfies it the other way, by
# *desaturating* instead of rotating the hue. The physical reading is a
# two-part one and the ramp is now that reading:
#
#   * the first thing a chipped material shows is **fresh unweathered
#     surface** - lighter than the dirty face around it and not coloured at
#     all. `CRACK_RGB` is that, and `DAMAGE_RIM_RGB` is the lip of it around
#     the chip.
#   * only once the panel is *critical* does anything glow, and what glows is
#     stress inside the fissure, which is incandescence: warm, and washing out
#     to white as it rises.
#
# Saturation is what does the separating now. Team orange is (1.00, 0.54,
# 0.13), saturation 0.87; `CRITICAL_RGB` is the same hue family at saturation
# 0.30 and 0.635 away in RGB, so it reads as "hot", never as "the orange
# team". Every stop still clears the 0.45 gate against both teams and the ramp
# is still monotone in luminance, so it still reads as one escalating thing.
CRACK_RGB = (0.760, 0.790, 0.840)
CRITICAL_RGB = (1.000, 0.820, 0.700)
FRACTURE_RGB = (1.000, 0.930, 0.870)
BREAK_FLASH_RGB = (1.000, 0.940, 0.960)
#: The broken lip around a chip: the bright edge where material was knocked
#: away. **This is the single strongest "it happened to the material" cue in
#: the wound** - a dark notch alone reads as a painted dot, and a dark notch
#: with a lit rim on it reads as a hole, because that is what a chip in a lit
#: solid does. It is state-independent on purpose: a broken edge does not get
#: hotter, it is just broken, so one shared material serves the whole arena.
DAMAGE_RIM_RGB = (0.800, 0.815, 0.855)
DAMAGE_RIM_ENERGY = 0.60
#: How far the lip stands proud of the chip **along the chord**.
DAMAGE_RIM_MARGIN = 0.070
#: And how tall it is radially, as a share of the panel's own thickness.
#:
#: **This is a separate constant because the first version did not have one
#: and the render showed why.** The lip was sized as the chip plus the margin
#: on both axes, which is `0.68 * 0.30 + 2 * 0.070 = 0.344` against a panel
#: 0.300 thick - so every wound stuck out past the top and bottom of the band
#: it was supposed to be a hole in, and the whole point of a lit rim inverted:
#: instead of a chip in a wall it read as a plate stuck on one. A crack has
#: been held to the canonical silhouette since Phase 4A by
#: `DAMAGE_CRACK_SPAN`; the lip needed the same rule and now has it, with
#: `test_a_wound_never_leaves_its_panel_radially` recomputing both.
DAMAGE_RIM_SPAN = 0.92

# Emission energy by damage state, in the same order as DAMAGE_STATES. The
# progression a viewer reads is this ramp times the crack count below it, not a
# recolour of the panel body, which keeps its own material throughout.
#
# **Halved for 4B.** The old ramp lit a saturated crimson bar at up to 4.0
# emission on an unshaded material, which is a light source sitting on a wall,
# and a light source sitting on a wall is what "UI annotation" means. Damage in
# 4B is a dark chip taken out of the material with a thin bright line in the
# bottom of it, so the bright part is small and the ramp does not have to shout.
DAMAGE_EMISSION_ENERGY: tuple[float, ...] = (0.00, 0.55, 1.30, 2.10, 0.00)
#: The chip is the part that reads as damage: unlit, darker than the panel,
#: recessed into the front face. It is what makes the crack look like it is in
#: something rather than on something.
DAMAGE_CHIP_RGB = (0.115, 0.130, 0.160)
#: **Wear below the first damage state, which is canonical and was not drawn.**
#:
#: `damage` events carry `fraction` - the panel's cumulative damage over its own
#: threshold - on every single collision, and Phase 4A read only the quantised
#: `panel_states` ledger. So a panel at 0.34 of its threshold was drawn exactly
#: like one that had never been touched, and on the outer shell that is almost
#: every panel: the final wall's threshold is high enough that at the final
#: struggle it is 64/66 healthy on 17964 and **66/66 healthy on 3762**, which
#: fails the brief's own five-part final-wall gate on "accumulated damage".
#:
#: Drawing it is reading the document, not inventing: 15, 28 and 3 outer panels
#: carry a non-zero fraction on the three candidates, up to 0.346, 0.233 and
#: 1.019. A worn panel loses its sheen and takes a scuff at its heaviest wound
#: before it ever gains a crack - which is what the Phase 4A comment said the
#: design wanted, and what quantising to five states prevented.
#:
#: The floor and the curve are both set by what is actually visible. A chip is
#: `DAMAGE_MARK_CHORD` wide, which is 7.4 px at the final framing, so a chip
#: scaled *linearly* by a wear of 0.07 is 0.4 px and there is no point drawing
#: it; the scale is the square root, which puts that same panel at 2.0 px. The
#: sheen loss carries the rest and needs no floor at all, because it is the
#: whole panel face rather than a notch in it.
DAMAGE_WEAR_FLOOR = 0.04
DAMAGE_WEAR_FACE_LOSS = 0.60
DAMAGE_WEAR_CHIP_SCALE = 0.85
DAMAGE_CHIP_DEPTH = 0.055
#: How much wider a chip gets per extra impact in its cluster, capped.
DAMAGE_CLUSTER_GROWTH = 0.34
DAMAGE_CLUSTER_GROWTH_MAX = 2.10
#: Two impacts closer than this along the chord are the same wound. Repeated
#: hits in one area then visibly build on one another instead of drawing a
#: second identical marker beside the first, which is the brief's own
#: requirement and the difference between wear and a tally.
#:
#: Swept rather than chosen. Across the three review candidates, half a ball
#: radius (0.26) merges so hard that only 2 to 7 panels in a whole run end up
#: with two distinct wounds and none ever has three - every panel becomes one
#: growing dent, which loses the "multiple connected cracks" the critical state
#: is supposed to read as. A quarter of that (0.065) barely merges at all and
#: the result is the row of identical bars 4B exists to remove. 0.13 - a
#: quarter of a ball *radius* - leaves 13 to 18 panels per run with two wounds
#: and a maximum of three, while the heaviest single wound still absorbs 9, 12
#: and 19 impacts.
DAMAGE_CLUSTER_CHORD = 0.13
#: Hairlines that run out of a wound once it is bad enough. They are derived
#: from the wound, not from new impact positions, so "multiple connected
#: cracks" stays connected to the one place the ball actually kept hitting.
DAMAGE_BRANCH_COUNT: tuple[int, ...] = (0, 0, 1, 2, 0)
DAMAGE_BRANCH_SPREAD_DEGREES = 26.0
DAMAGE_BRANCH_LENGTH = 0.62
#: **The connection in "connected crack network".** From `critical` upward a
#: seam runs along the chord from each shown wound to the next one, so a panel
#: with three wounds shows one fissure system rather than three separate
#: injuries. Below `critical` there is no seam: a `damaged` panel is supposed
#: to read as two local chips, and joining them would skip a state.
#:
#: It is derived entirely from the wound offsets, which are canonical impact
#: positions, so the network is still tied to where the ball actually hit -
#: the seam has no freedom of its own at all.
DAMAGE_SEAM_STATES: tuple[bool, ...] = (False, False, True, True, False)
DAMAGE_SEAM_WIDTH = 0.030
#: A seam shorter than this is inside the two chips it would join and drawing
#: it only thickens them.
DAMAGE_SEAM_MIN_CHORD = 0.16
#: The crack that runs out of a chip, as a fraction of the panel thickness. It
#: crosses the wall rather than sitting on the face, so it is visible on the
#: flank of the outer shells, where the flank is most of what is on screen.
# A crack is a `width x span*thickness` rectangle rolled by the tilt, and its
# rotated radial extent is `span*cos(tilt) + (width/thickness)*sin(tilt)`. At 34
# degrees that stays inside the panel for any span up to 1.128, so 1.10 is the
# longest crack that never puts a pixel outside the canonical silhouette - the
# same rule the 4A marks were held to, and the reason they had to be bars
# rather than lines. `test_a_crack_never_leaves_the_panel` recomputes it.
DAMAGE_CRACK_SPAN = 1.10
DAMAGE_CRACK_WIDTH = 0.035
#: A deterministic lean per crack, from the panel's own identity and the
#: cluster's index, so no two panels crack identically and no render differs.
DAMAGE_CRACK_TILT_DEGREES = 34.0
# How many of a panel's crack marks are shown in each state. The marks are
# placed at the panel's own canonical impact offsets, in the order the impacts
# happened, so damage appears where the ball actually hit it.
DAMAGE_CRACK_COUNT: tuple[int, ...] = (0, 2, 4, 6, 0)
# How wide a damage mark is along the panel's own chord. The mark spans the
# panel's full wall depth - its 0.30-unit face and its whole flank behind it -
# so at the final framing it is a 5.5 px wide bar 24 px tall on an 85 px panel,
# and four of them read as a damaged panel at phone size. It is exactly as
# thick as the panel radially, so a mark never puts a pixel outside the
# canonical silhouette.
DAMAGE_MARK_CHORD = 0.30
#: **Surface roughness, which the brief asks for at `damaged` and which no
#: amount of added geometry supplies.** A panel's material roughness rises
#: with how worn it is, so a beaten panel stops taking a clean specular
#: highlight before it has a single crack on it. It is a continuous read of
#: the same canonical `fraction` the scuff uses, clamped at 1.0 - fully rough.
DAMAGE_WEAR_ROUGHNESS = 0.55
#: And the state ladder on top of it, for panels past the wear range.
DAMAGE_STATE_ROUGHNESS: tuple[float, ...] = (0.00, 0.22, 0.40, 0.55, 0.00)
#: **Fractured: "separated crack planes, visible section boundaries, small
#: displaced-looking chunks".** The three sub-slabs a panel is built from are
#: each pushed back by a different amount once it fractures, so the section
#: boundaries throw their own edges and the slab reads as three pieces that
#: have shifted rather than one piece with two lines on it. Displacement is
#: *inward only* - a fractured panel still never occupies a pixel a healthy one
#: did not, which is the rule that keeps presentation off the collision
#: silhouette until the canonical break.
FRACTURE_SEGMENT_RECESS: tuple[float, ...] = (0.06, 0.22, 0.12)
#: **The brief's "tiny local Cyan/Orange stress tint" allowance.** When both
#: teams have damaged the same panel, its stress glow leans this far toward
#: whichever team has done more of it - and no further: the wall has to keep
#: looking like a wall, so the tint is a fifth of the way and it is on the
#: localised glow only, never on the panel body, the chip, the rim or the
#: crack. A panel one team damaged alone is not tinted at all, because there
#: is nothing being said by it.
DAMAGE_TEAM_TINT = 0.20
#: The minority team has to own at least this share of a panel's damage before
#: "both teams did this" is a true statement about it.
DAMAGE_TEAM_TINT_MIN_SHARE = 0.20
# `fractured` opens two gaps between the three sub-slabs. The gaps are cut out
# of the sub-slabs rather than made by pushing them apart, so the panel's two
# ends stay exactly where they were and a fractured panel never occupies a
# pixel a healthy one did not. 0.20 units is 3.5 px at the final framing and
# 13 px while its own shell is framed; 0.05, the first value tried, was 0.9 px
# and invisible.
FRACTURE_GAP = 0.20
# A roll about each sub-slab's own long axis. It changes nothing in silhouette
# and everything in shading, which is what makes a fractured panel look
# buckled rather than repainted.
FRACTURE_TILT_DEGREES = 9.0
FRACTURE_RECESS = 0.10

# --------------------------------------------------------------------------
# Overlay
# --------------------------------------------------------------------------

HOOK_TEXT = "WHO ESCAPES FIRST?"
HOOK_TOP_FRACTION = 0.082
HOOK_SIZE_FRACTION = 0.0315
#: **The hook leaves.** Phase 4A faded it from 1.0 to 0.22 starting at 3.4 s
#: and left it there: a ghost of the question sat over the whole race, which is
#: exactly the human review's complaint. It is now held solid for the brief's
#: 1.5-2.0 s, taken to nothing over half a second, and the label is *hidden*
#: rather than made transparent, so nothing of it can survive a colour grade.
HOOK_HOLD_SECONDS = 1.85
HOOK_FADE_SECONDS = 0.55
HOOK_FADE_TO = 0.0
#: After this the label is not drawn at all.
HOOK_GONE_SECONDS = HOOK_HOLD_SECONDS + HOOK_FADE_SECONDS

WINNER_SIZE_FRACTION = 0.052
#: The banner goes on whichever side of the frame the escaping ball is not on.
#: Phase 4A pinned it at 0.735 of the height, and on a candidate whose escape
#: happens low and right that is the payoff covered by its own caption.
WINNER_TOP_FRACTION = 0.735
WINNER_ALT_TOP_FRACTION = 0.150
WINNER_RISE_SECONDS = 0.22
#: The banner's own band, as a fraction of the height, used to decide which
#: end it goes to and to prove the escaping ball is not inside it.
WINNER_BAND_FRACTION = 0.105


#: How many points of the escapee's release flight the placement is tested at.
WINNER_RELEASE_SAMPLES = 25


def winner_banner_placement(document: dict[str, Any]) -> dict[str, Any]:
    """Which end of the frame the winner banner goes to, and why.

    Deterministic, and derived from the escapee's **whole release flight**
    rather than from its position at the escape instant.

    **Testing only the escape instant gives the wrong answer, and a rendered
    contact sheet is what caught it.** The banner appears at the escape and
    stays up through the 0.55 s release beat, during which the escapee keeps
    flying outward - it is the one ball with a canonical flight worth
    continuing, because there is nothing outside the arena for it to hit. On
    1176 the escape is at the bottom of the arena at y = 1317.9 px, which is
    93 px clear of the banner band, and 0.55 s later the ball is at 1418.7 px,
    which is inside it. The old check reported `clear_of_ball: True` for a
    frame in which the ball sits on the letters.

    So both candidate bands are tested against the ball's whole swept extent,
    the lower one is preferred, and the report says which was chosen.
    """
    _require_valid(document)
    escape = None
    for event in document["events"]:
        if event["kind"] == "escape":
            escape = event
    if escape is None:
        return {"placed": False}
    duration = float(document["summary"]["duration"])
    view = view_radius_at(document, float(escape["t"]))
    scale = pixels_per_unit(view)
    ball_px = float(document["config"]["ball_radius"]) * BALL_DRAW_SCALE * scale

    ys: list[float] = []
    ball_id = int(escape["ball_id"])
    for index in range(WINNER_RELEASE_SAMPLES):
        t = duration + RELEASE_SECONDS * index / (WINNER_RELEASE_SAMPLES - 1)
        point = position_at(document, ball_id, t)
        if point is None:
            continue
        ys.append(project(point, view)[1])
    if not ys:
        ys = [project(tuple(escape["position"]), view)[1]]
    low = min(ys) - ball_px
    high = max(ys) + ball_px

    def clear(top_fraction: float) -> bool:
        band_top = top_fraction * FRAME_HEIGHT
        band_bottom = band_top + WINNER_BAND_FRACTION * FRAME_HEIGHT
        return not (high > band_top and low < band_bottom)

    if clear(WINNER_TOP_FRACTION):
        top = WINNER_TOP_FRACTION
    elif clear(WINNER_ALT_TOP_FRACTION):
        top = WINNER_ALT_TOP_FRACTION
    else:
        # Neither end is clear. Take the one the ball is furthest from, and say
        # so rather than reporting a pass.
        def distance(top_fraction: float) -> float:
            band_top = top_fraction * FRAME_HEIGHT
            band_bottom = band_top + WINNER_BAND_FRACTION * FRAME_HEIGHT
            return min(abs(low - band_bottom), abs(high - band_top))

        top = max(
            (WINNER_TOP_FRACTION, WINNER_ALT_TOP_FRACTION), key=distance
        )
    band = (top * FRAME_HEIGHT, (top + WINNER_BAND_FRACTION) * FRAME_HEIGHT)
    return {
        "placed": True,
        "team_id": int(escape["team_id"]),
        "team_name": str(escape["team_name"]),
        "escape_y_px": ys[0],
        "release_y_px": [low + ball_px, high - ball_px],
        "swept_y_px": [low, high],
        "ball_radius_px": ball_px,
        "top_fraction": top,
        "band_px": list(band),
        "moved_to_top": top == WINNER_ALT_TOP_FRACTION,
        "clear_of_ball": clear(top),
    }


# --------------------------------------------------------------------------
# The candidate rule
# --------------------------------------------------------------------------

SHORTLIST_PATH = os.path.join(
    "docs", "validation", "category3_two_team_shell_race_v4a",
    "phase4a_shortlist.json"
)

CANDIDATE_RULE: dict[str, Any] = {
    "source": SHORTLIST_PATH,
    "duration_seconds": [20.0, 26.0],
    "first_spawn_seconds_preferred_max": 2.0,
    "first_spawn_seconds_max": 3.0,
    "first_spawn_seconds_reject_above": 3.0,
    "population_total": [12, 26],
    "min_team_population": 4,
    "flags": "none",
    "note": (
        "Six review renders drawn from the Phase 4A 20,000-seed population. "
        "The set spans both winning colours, founder and descendant winners, "
        "opening and break routes, and populations from the middle to the top "
        "of the band. Nothing in the rule mentions the finishing margin or the "
        "lead-change count: a rule that rewarded a narrow finish would select "
        "for arranged ones."
    ),
}

# The result of applying CANDIDATE_RULE, frozen so a test catches a drift in
# either the rule or the shortlist.
# The result of applying CANDIDATE_RULE to the Phase 4A shortlist, then
# choosing six for variety by hand. Each one is here for a different reason and
# the reason is named, because "the top six by some score" is exactly the
# selection the brief forbids:
#
#   17964  the biggest and the most even - 18 balls, nine each, 31 breaks and
#          25 of them paid for by both colours. The top candidate.
#    3762  the most back-and-forth: three population lead changes and three
#          frontier lead changes, which is the most in the eligible pool.
#   10943  a *founder* wins, 3.28 s after the other colour's last advance, and
#          the camera has been settled for 3.05 s when it happens. Seed 952 was
#          the first pick here - a founder winning 1.11 s after the other
#          colour's last advance - and it was dropped because its last frontier
#          advance lands 0.68 s before the escape, so the camera is still
#          opening out over the payoff.
#   17660  the closest finish in the pool: 0.36 s.
#   16020  the most cooperative damage - 34 breaks, 28 of them cross-team and
#          11 broken by the colour that did not do most of the work.
#    1176  the only break-route win in the six, and the deepest winner: a
#          fourth-generation descendant.
CANDIDATE_SEEDS: tuple[int, ...] = (17964, 3762, 10943, 17660, 16020, 1176)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def validate_document(document: dict[str, Any]) -> str:
    """Empty string if this consumer may draw the document, else the reason."""
    if str(document.get("schema", "")) != EXPECTED_SCHEMA_VERSION:
        return (
            f"schema is {document.get('schema')!r}, this renderer reads "
            f"{EXPECTED_SCHEMA_VERSION!r}"
        )
    if str(document.get("config_digest", "")) != EXPECTED_CONFIG_DIGEST:
        return "config digest is not the locked Phase 3B operating configuration"
    shells = document.get("shells", [])
    if len(shells) != EXPECTED_SHELL_COUNT:
        return (
            f"the visual proof is built for {EXPECTED_SHELL_COUNT} shells, "
            f"got {len(shells)}"
        )
    if not document.get("summary", {}).get("escaped", False):
        return "a proof candidate must reach a canonical escape"
    events = document.get("events", [])
    if not events:
        return "the document carries no events"
    previous = -math.inf
    for event in events:
        at = float(event["t"])
        if at < previous:
            return "canonical event order is not monotone in time"
        previous = at
    if not any(event["kind"] == "escape" for event in events):
        return "no canonical escape event"
    return ""


def _require_valid(document: dict[str, Any]) -> None:
    reason = validate_document(document)
    if reason:
        raise ValueError(reason)


# --------------------------------------------------------------------------
# The camera schedule
# --------------------------------------------------------------------------


def shell_material_radii(document: dict[str, Any]) -> tuple[float, ...]:
    """Each shell's outer material edge: its radius plus half its thickness."""
    return tuple(
        float(shell["radius"]) + 0.5 * float(shell["thickness"])
        for shell in document["shells"]
    )


def shell_view_radii(document: dict[str, Any]) -> tuple[float, ...]:
    """The framed radius at each stage: a shell's material edge times the pad.

    Proportional rather than additive, which is the whole of "constant frontier
    screen size": `pixels_per_unit` divides by the framed radius, so a framed
    radius proportional to the material edge makes the material edge's share of
    the frame the same number at every stage, exactly, with no fitting.
    """
    return tuple(r * (1.0 + VIEW_PAD_FRACTION) for r in shell_material_radii(document))


def zoom_ratio(document: dict[str, Any]) -> float:
    """Total zoom-out the camera actually performs, last stage over first.

    Not `radii[-1] / radii[0]`, which is the *shells'* ratio and was the number
    Phase 4A reported because its camera framed every shell in turn. Grouping
    the opening stage onto shell 1 is most of the 4B gain on its own: 2.80
    becomes 1.93, so the late arena is 45% larger relative to the opening than
    it was, before the frame fraction is raised at all.
    """
    stages = camera_stages(document)
    return float(stages[-1]["radius"]) / float(stages[0]["radius"])


def frontier_marks(document: dict[str, Any]) -> tuple[tuple[float, int], ...]:
    """`(t, region)` for each advance of the canonical high-water frontier.

    Read from the `shell_exit` stream and from nothing else. `to_region` is the
    region a ball moved into, so the first exit to region `k` is the first
    moment any ball is bounded by shell `k`. Region 5 - escaped - has no shell,
    so the progression stops at 4.

    This is the *race*, not the camera. Phase 4A framed one stage per mark,
    which is why the camera moved four times; `camera_stages` consumes these
    marks and moves twice.
    """
    limit = len(document["shells"]) - 1
    marks: list[tuple[float, int]] = []
    high_water = 0
    for event in document["events"]:
        if event["kind"] != "shell_exit":
            continue
        to_region = int(event["to_region"])
        while high_water < min(to_region, limit):
            high_water += 1
            marks.append((float(event["t"]), high_water))
    return tuple(marks)


def frontier_reached(document: dict[str, Any]) -> dict[int, float]:
    """The first instant the race's high-water frontier reached each region."""
    reached: dict[int, float] = {}
    for at, region in frontier_marks(document):
        reached.setdefault(region, at)
    return reached


def protected_instants(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Canonical moments a camera move may not run across.

    Every one is an event in the document, so the guard cannot drift from the
    thing it guards, and a reader can check any entry against the event stream.
    """
    _require_valid(document)
    out: list[dict[str, Any]] = []
    first_spawn = True
    for event in document["events"]:
        kind = event["kind"]
        if kind == "ball_spawn" and first_spawn:
            first_spawn = False
            out.append({"t": float(event["t"]), "why": "first clone"})
        elif kind == "panel_break":
            out.append(
                {
                    "t": float(event["t"]),
                    "why": f"break s{event['shell_id']}p{event['panel_id']}",
                }
            )
        elif kind == "near_miss" and float(
            event["arc_separation_ball_radii"]
        ) <= STRONG_NEAR_MISS_RADII:
            out.append(
                {
                    "t": float(event["t"]),
                    "why": f"near miss {float(event['arc_separation_ball_radii']):.2f}r",
                }
            )
        elif kind == "escape":
            out.append({"t": float(event["t"]), "why": "escape"})
    out.sort(key=lambda entry: (entry["t"], entry["why"]))
    return tuple(out)


def _guarded(start: float, guards: Sequence[float]) -> list[float]:
    """The protected instants a move starting at `start` would run across."""
    low = start - EVENT_GUARD_BEFORE_SECONDS
    high = start + FRAME_EASE_SECONDS + EVENT_GUARD_AFTER_SECONDS
    return [g for g in guards if low <= g <= high]


def _clear_start(
    wanted: float, floor: float, guards: Sequence[float]
) -> float:
    """The start nearest `wanted` whose whole move clears every guard.

    **Protection may only pull a transition earlier, never push it later, and
    measurement is what settled that.** The first version deferred a blocked
    move to just after the last guard in its window. On 17964 that put the
    final reframe 0.56 s late; the stage it was still holding is framed on
    shell 3 while the race had already entered region 4, so ball 7 spent 63
    frames outside the frame. On 3762 the same rule cost 98 frames. A camera
    that can put a ball off-screen is worse than one that moves over a near
    miss, and the trigger *is* the moment the old framing stops being big
    enough - so there is no slack after it to spend.

    Pulling earlier costs nothing: the camera consumes a finished document, so
    a lead is not clairvoyance, and `FRAME_LEAD_SECONDS` is already one. The
    nearest clear earlier start wins. `floor` keeps the windows disjoint and
    monotone. If nothing inside the cap is clear the unshifted start is used -
    an unprotected move is a far smaller fault than a late one.
    """
    if not _guarded(wanted, guards) and wanted >= floor:
        return wanted
    best: float | None = None
    for guard in guards:
        option = guard - EVENT_GUARD_BEFORE_SECONDS - FRAME_EASE_SECONDS
        if option < floor or option > wanted:
            continue
        if wanted - option > EVENT_GUARD_MAX_DEFER_SECONDS:
            continue
        if _guarded(option, guards):
            continue
        if best is None or option > best:
            best = option
    if best is None:
        return max(wanted, floor)
    return best


_STAGE_CACHE: dict[str, tuple[dict[str, Any], ...]] = {}


def camera_stages(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """The whole camera schedule: one entry per stage, outward and monotone.

    `start` is when the move into that stage begins and `settled` is when it
    ends. Stage 0 starts before the clip does, so both are 0.0 and the opening
    framing is already in place at frame one.

    Three properties hold by construction and are tested rather than assumed:
    the radii are strictly increasing, the windows never overlap, and no
    window contains a protected instant unless the deferral cap was reached.
    """
    _require_valid(document)
    key = str(document.get("digest", "")) or json.dumps(
        document["summary"], sort_keys=True)
    cached = _STAGE_CACHE.get(key)
    if cached is not None:
        return cached
    radii = shell_view_radii(document)
    reached = frontier_reached(document)
    guards = [entry["t"] for entry in protected_instants(document)]

    protected = protected_instants(document)
    stages: list[dict[str, Any]] = []
    previous_end = 0.0
    for index, (trigger, extent) in enumerate(CAMERA_STAGE_PLAN):
        if index == 0:
            stages.append(
                {
                    "stage": 0,
                    "trigger_region": None,
                    "extent_shell": extent,
                    "trigger_t": 0.0,
                    "start": 0.0,
                    "settled": 0.0,
                    "deferred": 0.0,
                    "radius": radii[extent],
                    "guard_conflicts": [],
                }
            )
            continue
        if trigger not in reached:
            # The race never got this far; the stage simply does not happen.
            continue
        trigger_t = reached[trigger]
        wanted = trigger_t - FRAME_LEAD_SECONDS
        start = _clear_start(wanted, previous_end, guards)
        deferred = start - wanted
        settled = start + FRAME_EASE_SECONDS
        previous_end = settled
        stages.append(
            {
                "stage": index,
                "trigger_region": trigger,
                "extent_shell": extent,
                "trigger_t": trigger_t,
                "start": start,
                "settled": settled,
                "deferred": deferred,
                "radius": radii[extent],
                # What the move could not be shifted clear of, named. On the
                # three review candidates this is only ever a near miss or a
                # break that the triggering crossing itself caused, within
                # 0.25 s of the trigger - there is no earlier slot because the
                # trigger is the moment the old framing stops being big enough.
                # It is never the first clone, a passage break or the escape.
                "guard_conflicts": [
                    dict(entry) for entry in protected
                    if start - EVENT_GUARD_BEFORE_SECONDS
                    <= entry["t"]
                    <= settled + EVENT_GUARD_AFTER_SECONDS
                ],
            }
        )
    result = tuple(stages)
    _STAGE_CACHE[key] = result
    return result


def frame_marks(document: dict[str, Any]) -> tuple[tuple[float, int], ...]:
    """`(start, stage)` for each camera transition. Stage 0 is not a move."""
    return tuple(
        (float(stage["start"]), int(stage["stage"]))
        for stage in camera_stages(document)
        if stage["stage"] > 0
    )


def camera_lock_time(document: dict[str, Any]) -> float:
    """The instant after which the camera never moves again."""
    stages = camera_stages(document)
    return float(stages[-1]["settled"]) if stages else 0.0


def static_tail_seconds(document: dict[str, Any]) -> float:
    """How long the composition is fixed before the winning escape."""
    escape = float(document["summary"]["escape_time"])
    return max(0.0, escape - camera_lock_time(document))


def _smoothstep(u: float) -> float:
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    return u * u * (3.0 - 2.0 * u)


def view_radius_at(document: dict[str, Any], t: float) -> float:
    """The framed world radius at `t`. Monotone non-decreasing by construction.

    Phase 4A summed one eased step per frontier advance, which let two advances
    overlap. The 4B schedule already guarantees the windows are disjoint, so
    this reads as what it is: hold a stage's radius, ease to the next, hold.
    The camera can only ever move outward, and it cannot move at all after
    `camera_lock_time`.
    """
    stages = camera_stages(document)
    radius = float(stages[0]["radius"])
    for stage in stages[1:]:
        previous = radius
        radius = previous + (float(stage["radius"]) - previous) * _smoothstep(
            (t - float(stage["start"])) / FRAME_EASE_SECONDS
        )
    return radius


def pixels_per_unit(view_radius: float, width: int = FRAME_WIDTH) -> float:
    """Exact, not fitted: `2*view_radius` occupies VIEW_DIAMETER_FRACTION of the frame."""
    return float(width) * VIEW_DIAMETER_FRACTION / (2.0 * view_radius)


def camera_distance(view_radius: float) -> float:
    """Where the eye sits for that framing, from the horizontal field of view."""
    half_width_units = view_radius / VIEW_DIAMETER_FRACTION
    return half_width_units / math.tan(math.radians(CAMERA_HFOV_DEGREES) * 0.5)


def project(
    point: Sequence[float],
    view_radius: float,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> tuple[float, float]:
    """A canonical `z = 0` position to a pixel, origin at the frame's top left.

    The z=0 plane is projected by a uniform scale even under the perspective
    camera, because the camera looks straight down -Z, so this is the
    renderer's projection and not an approximation of it.
    """
    scale = pixels_per_unit(view_radius, width)
    return (
        width * ARENA_CENTRE_X_FRACTION + float(point[0]) * scale,
        height * ARENA_CENTRE_Y_FRACTION - float(point[1]) * scale,
    )


def project_3d(
    point: Sequence[float],
    z: float,
    view_radius: float,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
) -> tuple[float, float]:
    """Project a point through the centred asymmetric perspective frustum."""
    distance = camera_distance(view_radius)
    scale = pixels_per_unit(view_radius, width) * distance / (distance - float(z))
    return (
        width * ARENA_CENTRE_X_FRACTION + float(point[0]) * scale,
        height * ARENA_CENTRE_Y_FRACTION - float(point[1]) * scale,
    )


def projected_shell_centres(view_radius: float) -> tuple[tuple[float, float], ...]:
    """Projected centres of the five thick slabs, sampled at slab mid-depth."""
    return tuple(project_3d((0.0, 0.0), -0.5 * depth, view_radius) for depth in PANEL_DEPTH)


def centre_alignment_report(
    document: dict[str, Any], fps: float = 60.0
) -> dict[str, Any]:
    """Measure shell-centre agreement on every rendered frame.

    The shell centres are sampled at their visual mid-depth, not merely at the
    shared front plane.  That is the measurement that exposes the old lateral
    camera's parallax and proves the off-axis frustum removed it.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    frame_count = int(math.ceil(duration * fps)) + 1
    maximum = 0.0
    worst_t = 0.0
    worst_centres: tuple[tuple[float, float], ...] = ()
    for frame in range(frame_count):
        t = min(duration, frame / fps)
        centres = projected_shell_centres(view_radius_at(document, t))
        for a in centres:
            for b in centres:
                error = math.hypot(a[0] - b[0], a[1] - b[1])
                if error > maximum:
                    maximum = error
                    worst_t = t
                    worst_centres = centres
    return {
        "fps": fps,
        "frames": frame_count,
        "maximum_disagreement_px": maximum,
        "worst_t": worst_t,
        "worst_centres": [list(point) for point in worst_centres],
        "target_px": 1.0,
        "preferred_px": 0.5,
        "passes": maximum <= 1.0,
    }


def alignment_moments(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Diagnostic still times around every centred frontier reframe."""
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    rows: list[dict[str, Any]] = [
        {"name": "frame_0", "t": 0.0, "why": "opening frame"}
    ]
    for index, (at, stage) in enumerate(frame_marks(document), start=1):
        rows.append(
            {
                "name": f"transition_{index}_mid",
                "t": max(0.0, at - FRAME_LEAD_SECONDS + 0.5 * FRAME_EASE_SECONDS),
                "why": f"mid-transition to frontier stage {stage}",
            }
        )
        rows.append(
            {
                "name": f"frontier_{index}_settled",
                "t": min(duration, at - FRAME_LEAD_SECONDS + FRAME_EASE_SECONDS),
                "why": f"after frontier stage {stage} settled",
            }
        )
    rows.append(
        {
            "name": "final_outer_section",
            "t": max(0.0, duration - 0.5),
            "why": "final outer-shell section",
        }
    )
    return rows


def flank_width(radius: float, depth: float, view_radius: float) -> float:
    """How wide a panel's receding side reads, in world units at the z=0 scale.

    A point at `z = -depth` and radius `r` projects to `r*D/(D+depth)`, so the
    flank runs from there out to the front face and is `r*depth/(D+depth)`
    wide. It lies *inside* the front face, which is why it can never cover a
    ball: every ball is at z=0, in front of every flank.
    """
    distance = camera_distance(view_radius)
    return radius * depth / (distance + depth)


def frontier_occupancy_report(document: dict[str, Any]) -> dict[str, Any]:
    """How big the frontier, the ball and the openings are at every stage.

    The review's second, third and fourth findings are all one measurement: at
    each frontier stage, how much of the frame does the shell the viewer is
    being asked to care about actually fill? This answers it per stage, against
    both the raw frame width and the brief's "usable screen width" - the widest
    horizontally centred band that clears the action rail - because the two
    differ by a factor of 1.47 and a bare percentage would be unreadable.

    `ball_px` is the *drawn* ball, `BALL_DRAW_SCALE` included, because that is
    the object a viewer sees; `ball_physical_px` is the collision ball, which is
    what has to fit through `gap_px`.
    """
    _require_valid(document)
    material = shell_material_radii(document)
    views = shell_view_radii(document)
    ball_radius = float(document["config"]["ball_radius"])
    usable_px = USABLE_WIDTH_FRACTION * FRAME_WIDTH

    def row_for(stage: int, shell_index: int) -> dict[str, Any]:
        shell = document["shells"][shell_index]
        view = views[shell_index]
        scale = pixels_per_unit(view)
        diameter_px = 2.0 * material[shell_index] * scale
        gap = min(float(o["gap_chord"]) for o in shell["openings"])
        depth = PANEL_DEPTH[shell_index]
        return {
            "stage": stage,
            "shell_id": int(shell["shell_id"]),
            "view_radius": view,
            "material_radius": material[shell_index],
            "pixels_per_unit": scale,
            "frontier_diameter_px": diameter_px,
            "frontier_over_frame_width": diameter_px / FRAME_WIDTH,
            "frontier_over_usable_width": diameter_px / usable_px,
            "frontier_over_frame_height": diameter_px / FRAME_HEIGHT,
            "ball_px": 2.0 * ball_radius * BALL_DRAW_SCALE * scale,
            "ball_physical_px": 2.0 * ball_radius * scale,
            "opening_px": gap * scale,
            "wall_px": (
                float(shell["thickness"])
                + flank_width(float(shell["radius"]), depth, view)
            ) * scale,
            "panel_chord_px": float(shell["chord_length"]) * scale,
        }

    # **The stages are the camera's, not the arena's.** Phase 4A had one per
    # shell so the two were the same list; 4B frames three of the five, and
    # reporting all five as "stages" would quote a ball size at a framing the
    # viewer is never shown. The per-shell arithmetic is kept below it, because
    # "how big would shell 2 be if it were framed" is still worth being able to
    # look up - it is just not a stage.
    rows = [
        row_for(int(stage["stage"]), int(stage["extent_shell"]))
        for stage in camera_stages(document)
    ]
    per_shell = [row_for(index, index) for index in range(len(document["shells"]))]
    fractions = [row["frontier_over_frame_width"] for row in rows]
    return {
        "frame": [FRAME_WIDTH, FRAME_HEIGHT],
        "usable_width_fraction": USABLE_WIDTH_FRACTION,
        "target_frame_width_fraction": FRONTIER_WIDTH_FRACTION,
        "stages": rows,
        "per_shell": per_shell,
        "min_frontier_over_frame_width": min(fractions),
        "max_frontier_over_frame_width": max(fractions),
        "frontier_fraction_spread": max(fractions) - min(fractions),
        "zoom_ratio": zoom_ratio(document),
        "ball_px_first": rows[0]["ball_px"],
        "ball_px_last": rows[-1]["ball_px"],
    }


def centring_report(document: dict[str, Any], samples: int = 240) -> dict[str, Any]:
    """Where the arena sits in the frame, and whether it ever moves sideways.

    Two numbers the human review asked for and Phase 3B could not answer. The
    first is the arena's own centre as a fraction of the frame width, which is
    0.500 by construction now and was 0.420. The second is the largest lateral
    movement of that centre over the whole run, which must be exactly zero: the
    camera only ever changes its distance, so the world centre projects to the
    same pixel on every frame of every candidate.

    `rail_clearance_px` is the gap between the outermost shell's drawn material
    and the conservative action rail at the final framing, which is the single
    tightest constraint the centred composition has.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    centres: list[tuple[float, float]] = []
    for index in range(samples + 1):
        t = duration * index / samples
        centres.append(project((0.0, 0.0), view_radius_at(document, t)))
    xs = [c[0] for c in centres]
    ys = [c[1] for c in centres]
    material = shell_material_radii(document)
    final_scale = pixels_per_unit(shell_view_radii(document)[-1])
    outer_px = material[-1] * final_scale
    rail_left = 0.840 * FRAME_WIDTH
    return {
        "samples": samples + 1,
        "arena_centre_x_fraction": ARENA_CENTRE_X_FRACTION,
        "arena_centre_y_fraction": ARENA_CENTRE_Y_FRACTION,
        "arena_centre_px": [xs[0], ys[0]],
        "lateral_offset_from_frame_centre_px": xs[0] - 0.5 * FRAME_WIDTH,
        "max_lateral_movement_px": max(xs) - min(xs),
        "max_vertical_movement_px": max(ys) - min(ys),
        "outer_material_radius_px": outer_px,
        "rail_left_px": rail_left,
        "rail_clearance_px": rail_left - (0.5 * FRAME_WIDTH + outer_px),
        "left_margin_px": 0.5 * FRAME_WIDTH - outer_px,
        "centred": abs(ARENA_CENTRE_X_FRACTION - 0.5) < 1e-9,
        "stationary": (max(xs) - min(xs)) < 1e-9 and (max(ys) - min(ys)) < 1e-9,
    }


# --------------------------------------------------------------------------
# Team colour
# --------------------------------------------------------------------------


def team_palette(document: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """One colour per ball, from `team_id` and `generation` and nothing else.

    A ball's hue is its team's hue, exactly, for every generation. That is the
    whole rule, and it is deliberately duller than Phase 3B's per-family
    palette: the video's question is "which colour gets out first", and a
    palette that answers "which family is this" instead answers a question
    nobody asked while making the one that matters harder.

    Generation reads as emission only. A great-great-grandchild is the same
    cyan as its founder and glows about a third brighter, which separates
    siblings inside a knot without ever putting a third hue on screen.

    `team_id` is on every ball record and is set by the simulation's labelling
    permutation, so this is a pure function of the document and two renders of
    one seed tint the same ball the same colour.
    """
    palette: dict[int, dict[str, Any]] = {}
    for ball in document["balls"]:
        ball_id = int(ball["ball_id"])
        team = int(ball["team_id"])
        generation = int(ball["generation"])
        energy = min(
            GENERATION_ENERGY_MAX, 1.0 + GENERATION_ENERGY_STEP * generation
        )
        palette[ball_id] = {
            "team": team,
            "team_name": TEAM_NAMES[team],
            "rgb": TEAM_RGB[team],
            "energy": energy,
            "generation": generation,
        }
    return palette


def team_of(document: dict[str, Any]) -> dict[int, int]:
    """Ball id to team index, for consumers that only need the label."""
    return {int(ball["ball_id"]): int(ball["team_id"]) for ball in document["balls"]}


def team_population_at(document: dict[str, Any], t: float) -> tuple[int, ...]:
    """How many balls of each team have been born by `t`."""
    counts = [0] * len(TEAM_NAMES)
    for ball in document["balls"]:
        if float(ball["birth_time"]) <= t:
            counts[int(ball["team_id"])] += 1
    return tuple(counts)


# --------------------------------------------------------------------------
# Reading the document back
# --------------------------------------------------------------------------


def live_balls_at(document: dict[str, Any], t: float) -> list[int]:
    """Ball ids that have been born by `t`, in birth order."""
    out = []
    for ball in document["balls"]:
        if float(ball["birth_time"]) <= t:
            out.append(int(ball["ball_id"]))
    return out


def positions_at(document: dict[str, Any], t: float) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for ball_id in live_balls_at(document, t):
        point = position_at(document, ball_id, t)
        if point is not None:
            out[ball_id] = point
    return out


def panel_impact_offsets(document: dict[str, Any]) -> dict[tuple[int, int], list[float]]:
    """Where each panel was actually hit, along its own chord, in time order.

    This is what makes a crack appear at an impact rather than at a decorative
    position: `panel_local_offset` is on every canonical collision event and is
    the contact's position along the panel measured from its centre.
    """
    out: dict[tuple[int, int], list[float]] = {}
    for event in document["events"]:
        if event["kind"] != "collision":
            continue
        key = (int(event["shell_id"]), int(event["panel_id"]))
        out.setdefault(key, []).append(float(event["panel_local_offset"]))
    return out


def damage_counts_at(document: dict[str, Any], t: float) -> dict[str, int]:
    """How many panels are in each canonical state at `t`, across all shells."""
    counts = {state: 0 for state in DAMAGE_STATES}
    total = 0
    for shell in document["shells"]:
        open_slots = set(int(s) for s in shell["open_slots"])
        for panel_id in range(int(shell["panel_count"])):
            if panel_id in open_slots:
                continue
            total += 1
            counts[panel_state_at(document, int(shell["shell_id"]), panel_id, t)] += 1
    counts["panels"] = total
    return counts


# --------------------------------------------------------------------------
# Geometry, measured
# --------------------------------------------------------------------------


def shell_geometry_report(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Per shell: how big its features are, at its own framing and at the last.

    Two columns matter and they answer different questions. `at_own_stage` is
    what the viewer sees while that shell is the frontier and the camera is
    framed on it; `at_final_stage` is what it looks like once the camera has
    opened out to the whole arena, which is where the five layers have to look
    different from each other.
    """
    radii = shell_view_radii(document)
    final_radius = radii[-1]
    out: list[dict[str, Any]] = []
    for shell in document["shells"]:
        index = int(shell["shell_id"])
        radius = float(shell["radius"])
        thickness = float(shell["thickness"])
        depth = PANEL_DEPTH[index]
        own = radii[index]
        entry: dict[str, Any] = {
            "shell_id": index,
            "radius": radius,
            "panel_count": int(shell["panel_count"]),
            "panels": int(shell["panel_count"]) - len(shell["open_slots"]),
            "openings": len(shell["openings"]),
            "open_fraction": len(shell["open_slots"]) / float(shell["panel_count"]),
            "chord_length": float(shell["chord_length"]),
            "gap_chord": min(float(o["gap_chord"]) for o in shell["openings"]),
            "depth": depth,
        }
        for label, view in (("at_own_stage", own), ("at_final_stage", final_radius)):
            scale = pixels_per_unit(view)
            flank = flank_width(radius, depth, view)
            entry[label] = {
                "view_radius": view,
                "pixels_per_unit": scale,
                "face_px": thickness * scale,
                "flank_px": flank * scale,
                "wall_px": (thickness + flank) * scale,
                "chord_px": float(shell["chord_length"]) * scale,
                "gap_px": entry["gap_chord"] * scale,
                "ring_radius_px": radius * scale,
            }
        out.append(entry)
    return out


def composition_report(document: dict[str, Any], samples: int = 240) -> dict[str, Any]:
    """Framing over the whole run: what fills the frame, and when it moves.

    `structure_occupancy` is the honest empty-space number. It is the fraction
    of the frame that lies inside the outermost shell with any material in
    shot, so it counts the shells that sit in the vertical bands at the tighter
    framings and does not count the bands that are genuinely dark at the last
    one.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    radii = shell_view_radii(document)
    marks = frame_marks(document)
    ball_radius = float(document["config"]["ball_radius"])

    moving = 0
    rows: list[dict[str, Any]] = []
    previous = None
    for index in range(samples + 1):
        t = duration * index / samples
        view = view_radius_at(document, t)
        scale = pixels_per_unit(view)
        if previous is not None and abs(view - previous) > 1e-9:
            moving += 1
        previous = view
        # Half-extents of the frame in world units.
        half_w = 0.5 * FRAME_WIDTH / scale
        half_h = 0.5 * FRAME_HEIGHT / scale
        centre_x = (ARENA_CENTRE_X_FRACTION - 0.5) * FRAME_WIDTH / scale
        centre_y = (0.5 - ARENA_CENTRE_Y_FRACTION) * FRAME_HEIGHT / scale
        # The outermost shell with material anywhere inside the frame.
        visible = 0.0
        for shell in document["shells"]:
            ring = float(shell["radius"]) + 0.5 * float(shell["thickness"])
            nearest_x = max(0.0, abs(centre_x) - half_w)
            nearest_y = max(0.0, abs(centre_y) - half_h)
            if math.hypot(nearest_x, nearest_y) <= ring:
                visible = max(visible, ring)
        rows.append(
            {
                "t": t,
                "view_radius": view,
                "pixels_per_unit": scale,
                "ball_px": 2.0 * ball_radius * BALL_DRAW_SCALE * scale,
                "halo_px": 2.0 * ball_radius * BALL_DRAW_SCALE * HALO_SCALE * scale,
                "structure_occupancy": _disc_frame_fraction(visible * scale),
            }
        )

    moving_fraction = moving / float(samples)
    static_tail = duration - (marks[-1][0] - FRAME_LEAD_SECONDS + FRAME_EASE_SECONDS) \
        if marks else duration
    return {
        "duration": duration,
        "frame_marks": [{"t": at, "stage": stage} for at, stage in marks],
        "stage_view_radii": list(radii),
        "camera_moving_fraction": moving_fraction,
        "camera_moving_seconds": moving_fraction * duration,
        "static_tail_seconds": static_tail,
        "ball_px_first_frame": rows[0]["ball_px"],
        "ball_px_last_frame": rows[-1]["ball_px"],
        "halo_px_last_frame": rows[-1]["halo_px"],
        "structure_occupancy_min": min(r["structure_occupancy"] for r in rows),
        "structure_occupancy_mean": sum(r["structure_occupancy"] for r in rows) / len(rows),
        "structure_occupancy_first": rows[0]["structure_occupancy"],
        "structure_occupancy_last": rows[-1]["structure_occupancy"],
        "samples": rows,
    }


def _disc_frame_fraction(radius_px: float) -> float:
    """What fraction of the 1080x1920 frame a disc of that pixel radius covers.

    Monte-Carlo-free: the disc is centred at the composition point and the
    frame is a rectangle, so the overlap is computed by integrating the disc's
    chord against the frame's vertical extent.
    """
    if radius_px <= 0.0:
        return 0.0
    cx = ARENA_CENTRE_X_FRACTION * FRAME_WIDTH
    cy = ARENA_CENTRE_Y_FRACTION * FRAME_HEIGHT
    steps = 480
    lo = max(0.0, cy - radius_px)
    hi = min(float(FRAME_HEIGHT), cy + radius_px)
    if hi <= lo:
        return 0.0
    area = 0.0
    step = (hi - lo) / steps
    for index in range(steps):
        y = lo + (index + 0.5) * step
        half = math.sqrt(max(0.0, radius_px * radius_px - (y - cy) ** 2))
        left = max(0.0, cx - half)
        right = min(float(FRAME_WIDTH), cx + half)
        area += max(0.0, right - left) * step
    return area / float(FRAME_WIDTH * FRAME_HEIGHT)


# --------------------------------------------------------------------------
# Safe area
# --------------------------------------------------------------------------


def safe_area_report(
    document: dict[str, Any],
    config: SafeAreaConfig = DEFAULT_SAFE_AREA,
    fps: float = 30.0,
) -> dict[str, Any]:
    """Does anything the viewer needs sit under the player's own controls?

    Two readings. The **arena** is geometry and is checked at the final
    framing, where it is largest: the outermost shell's material circle against
    each region, reported as the clearance in pixels, negative if it intrudes.
    The **balls** are checked over time, because a ball is where the viewer is
    looking and a ball under the action rail is a ball that is not there.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    final_view = shell_view_radii(document)[-1]
    scale = pixels_per_unit(final_view)
    outer = float(document["shells"][-1]["radius"]) + 0.5 * float(
        document["shells"][-1]["thickness"]
    )
    cx = ARENA_CENTRE_X_FRACTION * FRAME_WIDTH
    cy = ARENA_CENTRE_Y_FRACTION * FRAME_HEIGHT
    radius_px = outer * scale

    regions: list[dict[str, Any]] = []
    for region in config.regions:
        left, top, right, bottom = region.rect(FRAME_WIDTH, FRAME_HEIGHT)
        # Signed clearance from the disc to the rectangle: positive is clear.
        dx = max(left - cx, 0.0, cx - right)
        dy = max(top - cy, 0.0, cy - bottom)
        if dx == 0.0 and dy == 0.0:
            clearance = -radius_px
        else:
            clearance = math.hypot(dx, dy) - radius_px
        regions.append(
            {
                "region": region.name,
                "clearance_px": clearance,
                "clear": clearance > 0.0,
            }
        )

    ball_radius_px = float(document["config"]["ball_radius"]) * BALL_DRAW_SCALE * scale
    frames = max(1, int(round(duration * fps)))
    hidden_total = 0
    hidden_run = 0
    worst_run = 0
    hidden_by_region: dict[str, int] = {r.name: 0 for r in config.regions}
    for index in range(frames + 1):
        t = duration * index / frames
        view = view_radius_at(document, t)
        any_hidden = False
        for point in positions_at(document, t).values():
            px, py = project(point, view)
            for region in config.regions:
                covered = _disc_rect_fraction(px, py, ball_radius_px, region)
                if covered >= config.ball_hidden_fraction:
                    hidden_by_region[region.name] += 1
                    any_hidden = True
        if any_hidden:
            hidden_total += 1
            hidden_run += 1
            worst_run = max(worst_run, hidden_run)
        else:
            hidden_run = 0

    return {
        "safe_area": config.name,
        "fingerprint": config.fingerprint(),
        "final_view_radius": final_view,
        "pixels_per_unit": scale,
        "arena_radius_px": radius_px,
        "arena_regions": regions,
        "arena_clear": all(entry["clear"] for entry in regions),
        "min_clearance_px": min(entry["clearance_px"] for entry in regions),
        "ball_hidden_frames": hidden_total,
        "ball_hidden_seconds": hidden_total / fps,
        "ball_hidden_longest_seconds": worst_run / fps,
        "ball_hidden_budget_seconds": config.ball_hidden_budget_seconds,
        "ball_hidden_by_region": hidden_by_region,
        "ball_pass": (worst_run / fps) <= config.ball_hidden_budget_seconds,
    }


def _disc_rect_fraction(px: float, py: float, radius: float, region: Region) -> float:
    """Roughly how much of a disc falls inside a rectangle. Sampled on a grid.

    Exactness is not the question here - the gate is "half the ball or more" -
    and a 9x9 grid over the disc's bounding box answers that to about 1%.
    """
    left, top, right, bottom = region.rect(FRAME_WIDTH, FRAME_HEIGHT)
    if px + radius < left or px - radius > right:
        return 0.0
    if py + radius < top or py - radius > bottom:
        return 0.0
    inside = 0
    total = 0
    steps = 9
    for iy in range(steps):
        for ix in range(steps):
            x = px + radius * (2.0 * (ix + 0.5) / steps - 1.0)
            y = py + radius * (2.0 * (iy + 0.5) / steps - 1.0)
            if (x - px) ** 2 + (y - py) ** 2 > radius * radius:
                continue
            total += 1
            if left <= x <= right and top <= y <= bottom:
                inside += 1
    return inside / float(total) if total else 0.0


def _disc_offframe_fraction(px: float, py: float, radius: float) -> float:
    """How much of a drawn disc falls outside the frame rectangle itself.

    **New in 4C and the reason it is new.** Up to 4B the framed arena was
    always narrower than the frame, so the frame edge could never hide
    anything and the only way to lose a subject was the Shorts action rail.
    Above `FRONTIER_WIDTH_FRACTION = 1.0` the arena is *wider* than the frame
    by construction and the edge becomes the binding constraint - so a report
    that still only measured the rail would pass a framing that cropped the
    winning escape clean off the screen.

    Sampled on the same 9x9 grid as `_disc_rect_fraction` so the two numbers
    are comparable, and 0.0 means the whole drawn ball is on screen.
    """
    if radius <= 0.0:
        inside = 0.0 <= px <= FRAME_WIDTH and 0.0 <= py <= FRAME_HEIGHT
        return 0.0 if inside else 1.0
    inside = 0
    total = 0
    steps = 9
    for iy in range(steps):
        for ix in range(steps):
            x = px + radius * (2.0 * (ix + 0.5) / steps - 1.0)
            y = py + radius * (2.0 * (iy + 0.5) / steps - 1.0)
            if (x - px) ** 2 + (y - py) ** 2 > radius * radius:
                continue
            total += 1
            if 0.0 <= x <= FRAME_WIDTH and 0.0 <= y <= FRAME_HEIGHT:
                inside += 1
    return 1.0 - inside / float(total) if total else 1.0


# --------------------------------------------------------------------------
# Phase 4B: damage, fracture and flood-through, specified once
# --------------------------------------------------------------------------
#
# Everything below is the *specification* the GDScript renderer mirrors. The
# Phase 4A post-mortem is the reason it is written down here at all: the
# 1.778x frustum error survived three phases because the only test compared a
# Python constant with a GDScript constant and both copies were wrong the same
# way. So these are not constants - they are derivations from the canonical
# event stream, and `multishell_visual_cli audit` makes the scene emit what it
# actually built so Python can diff it against what this module says it should
# have built. Two files agreeing is not a measurement; a render agreeing with a
# derivation is.


def _panel_key(shell_id: int, panel_id: int) -> str:
    return "%d:%d" % (int(shell_id), int(panel_id))


def panel_damage_clusters(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Where each panel is worn, from where the ball actually hit it.

    A cluster is a wound. Impacts land along the panel's own chord at
    `panel_local_offset`, which is canonical; two impacts within
    `DAMAGE_CLUSTER_CHORD` of each other are the same wound and the second one
    deepens the first rather than drawing a second marker beside it. The first
    impact anchors the cluster, so the result depends only on the collision
    order and is exactly reproducible.

    That "repeated impacts in similar areas visibly build on one another" is
    the brief's requirement, and it is also the difference between damage that
    reads as wear and damage that reads as a tally of hits.
    """
    _require_valid(document)
    clusters: dict[str, list[dict[str, Any]]] = {}
    for event in document["events"]:
        if event["kind"] != "collision":
            continue
        key = _panel_key(event["shell_id"], event["panel_id"])
        offset = float(event["panel_local_offset"])
        row = clusters.setdefault(key, [])
        for cluster in row:
            if abs(cluster["offset"] - offset) <= DAMAGE_CLUSTER_CHORD:
                cluster["weight"] += 1
                cluster["last_t"] = float(event["t"])
                break
        else:
            row.append(
                {
                    "offset": offset,
                    "weight": 1,
                    "first_t": float(event["t"]),
                    "last_t": float(event["t"]),
                    "index": len(row),
                }
            )
    for key, row in clusters.items():
        shell_id, panel_id = (int(part) for part in key.split(":"))
        for cluster in row:
            cluster["growth"] = min(
                DAMAGE_CLUSTER_GROWTH_MAX,
                1.0 + DAMAGE_CLUSTER_GROWTH * (int(cluster["weight"]) - 1),
            )
            # A deterministic lean, so no two panels crack the same way and no
            # two renders of one seed differ. The parity of the panel's own
            # identity plus the cluster index is the whole of it.
            cluster["tilt_sign"] = 1 if (
                shell_id * 7 + panel_id * 3 + int(cluster["index"])
            ) % 2 == 0 else -1
    return clusters


def panel_wear(document: dict[str, Any]) -> dict[str, list[list[float]]]:
    """`[t, fraction]` per panel, from the canonical `damage` stream.

    `fraction` is cumulative damage over the panel's own threshold and is on
    every damage event, so this is the continuous version of the five-state
    ledger the renderer already reads - not a second opinion about it.
    """
    _require_valid(document)
    out: dict[str, list[list[float]]] = {}
    for event in document["events"]:
        if event["kind"] != "damage":
            continue
        key = _panel_key(event["shell_id"], event["panel_id"])
        out.setdefault(key, []).append(
            [float(event["t"]), float(event["fraction"])]
        )
    return out


def panel_wear_at(
    document: dict[str, Any], shell_id: int, panel_id: int, t: float
) -> float:
    """How worn a panel is at `t`, as a fraction of its own break threshold."""
    rows = panel_wear(document).get(_panel_key(shell_id, panel_id), [])
    wear = 0.0
    for at, fraction in rows:
        if at <= t:
            wear = fraction
        else:
            break
    return wear


def wear_report(document: dict[str, Any]) -> dict[str, Any]:
    """What the final wall shows at the final struggle, before and after.

    The number the brief's five-part gate turns on: how many panels of the
    outermost shell a viewer can see have been hit.
    """
    _require_valid(document)
    outer = document["shells"][-1]
    shell_id = int(outer["shell_id"])
    moment = None
    for entry in event_moments(document):
        if entry["name"] == "h_final_wall":
            moment = float(entry["t"])
    if moment is None:
        moment = float(document["summary"]["escape_time"])
    states: dict[str, int] = {}
    worn = 0
    touched = 0
    worst = 0.0
    for panel_id in range(int(outer["panel_count"])):
        state = panel_state_at(document, shell_id, panel_id, moment)
        states[state] = states.get(state, 0) + 1
        wear = panel_wear_at(document, shell_id, panel_id, moment)
        worst = max(worst, wear)
        if state == "healthy" and wear >= DAMAGE_WEAR_FLOOR:
            worn += 1
        if state == "healthy" and wear > 0.0:
            touched += 1
    marked = sum(count for state, count in states.items() if state != "healthy")
    return {
        "t": moment,
        "shell_id": shell_id,
        "panels": int(outer["panel_count"]),
        "states": states,
        "non_healthy": marked,
        "worn_healthy": worn,
        "touched_healthy": touched,
        "visibly_marked": marked + worn,
        "worst_wear": worst,
        "wear_floor": DAMAGE_WEAR_FLOOR,
    }


def visible_damage_clusters(
    document: dict[str, Any], shell_id: int, panel_id: int, state_index: int,
    wear: float = 0.0,
) -> list[dict[str, Any]]:
    """The clusters a panel draws in a given damage state, worst wound first.

    `DAMAGE_CRACK_COUNT` says how many; which ones is decided by weight, then
    by the order the wounds appeared. A panel that has been hit eight times in
    one place and once elsewhere shows the deep one first, which is what makes
    the damage look like it happened to the material.

    Below the first damage state a panel with canonical wear at or above
    `DAMAGE_WEAR_FLOOR` still shows its heaviest wound - as a scuff, the chip
    alone with no crack - which is what puts marks on a final wall that the
    five-state ledger calls entirely healthy.
    """
    row = panel_damage_clusters(document).get(_panel_key(shell_id, panel_id), [])
    wanted = int(DAMAGE_CRACK_COUNT[state_index])
    if state_index == 0 and wear >= DAMAGE_WEAR_FLOOR and row:
        wanted = 1
    order = sorted(row, key=lambda c: (-int(c["weight"]), int(c["index"])))
    return order[:wanted]


def wound_seams(
    document: dict[str, Any], shell_id: int, panel_id: int, state_index: int,
    wear: float = 0.0,
) -> list[dict[str, float]]:
    """The fissures that join a panel's wounds into one crack network.

    The brief's `critical` state asks for a *connected* crack network, and up
    to 4B a panel with three wounds drew three unconnected injuries however bad
    it got - the count went up, the structure did not change. A seam is the
    link: from `critical` upward, consecutive shown wounds **in chord order**
    are joined along the chord.

    It invents nothing. The endpoints are two canonical impact positions and
    the state comes from the canonical ledger, so the network is as tied to
    where the ball actually hit as the wounds are. Seams shorter than
    `DAMAGE_SEAM_MIN_CHORD` are dropped because they would be inside the two
    chips they join.
    """
    if not DAMAGE_SEAM_STATES[state_index]:
        return []
    shown = visible_damage_clusters(document, shell_id, panel_id, state_index, wear)
    if len(shown) < 2:
        return []
    order = sorted(shown, key=lambda cluster: float(cluster["offset"]))
    seams: list[dict[str, float]] = []
    for low, high in zip(order, order[1:]):
        a = float(low["offset"])
        b = float(high["offset"])
        length = abs(b - a)
        if length < DAMAGE_SEAM_MIN_CHORD:
            continue
        seams.append({
            "centre": 0.5 * (a + b),
            "length": length,
            "from_index": int(low["index"]),
            "to_index": int(high["index"]),
        })
    return seams


def panel_damage_teams(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Which team has done a panel's damage, from `team_cumulative`.

    The brief allows "a tiny local Cyan/Orange stress tint" where both teams
    contributed. This is the read that decides it, and it is a read: every
    `damage` event carries the running per-team totals already, so nothing is
    accumulated here that the simulation did not publish.

    `both` is deliberately not "the minority is non-zero" - a single glancing
    hit out of nineteen is not two teams wearing a panel down together, and a
    tint that fired on it would be noise. `DAMAGE_TEAM_TINT_MIN_SHARE` is the
    share the minority has to hold.
    """
    _require_valid(document)
    out: dict[str, dict[str, Any]] = {}
    for event in document["events"]:
        if event["kind"] != "damage":
            continue
        totals = [float(value) for value in event["team_cumulative"]]
        out[_panel_key(event["shell_id"], event["panel_id"])] = {
            "team_cumulative": totals,
            "total": sum(totals),
        }
    for row in out.values():
        totals = row["team_cumulative"]
        total = row["total"]
        lead = max(range(len(totals)), key=lambda index: totals[index])
        minority = (total - totals[lead]) / total if total > 0.0 else 0.0
        row["lead_team"] = lead
        row["minority_share"] = minority
        row["both"] = minority >= DAMAGE_TEAM_TINT_MIN_SHARE
        row["tint"] = DAMAGE_TEAM_TINT if row["both"] else 0.0
    return out


def panel_roughness(
    shell_id: int, state_index: int, wear: float = 0.0
) -> float:
    """A worn panel stops taking a clean highlight before it ever cracks.

    The brief's `damaged` state asks for "subtle surface roughness", which is
    the one part of a wound that no added geometry can supply: it is a material
    property of the whole face, not a shape on it. Continuous in the canonical
    `fraction` below the first damage state and stepped by the ledger above it,
    so the two halves of the same read meet without a discontinuity.
    """
    base = float(SHELL_ROUGHNESS[shell_id])
    added = DAMAGE_STATE_ROUGHNESS[state_index]
    if state_index == 0:
        added = DAMAGE_WEAR_ROUGHNESS * min(1.0, max(0.0, wear))
    return min(1.0, base + added)


def break_fragments(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The few substantial chunks a panel comes apart into, per break.

    Presentation only: nothing here is read by the simulation, no fragment has
    a collider, and `test_break_fragments_cannot_reach_the_physics` is the
    check that keeps it that way. The chunks are laid out along the panel's own
    chord rather than thrown from its centre, because a slab that fails breaks
    into pieces of itself - that is the entire difference between this and the
    eight hashed sparks it replaces.
    """
    _require_valid(document)
    shells = {int(shell["shell_id"]): shell for shell in document["shells"]}
    out: dict[str, list[dict[str, Any]]] = {}
    for event in document["events"]:
        if event["kind"] != "panel_break":
            continue
        shell_id = int(event["shell_id"])
        panel_id = int(event["panel_id"])
        shell = shells[shell_id]
        chord = float(shell["chord_length"])
        key = _panel_key(shell_id, panel_id)
        pieces: list[dict[str, Any]] = []
        for index in range(BREAK_FRAGMENT_COUNT):
            # Evenly along the chord, so the chunks tile the panel they came
            # from and the viewer reads them as its pieces.
            share = (index + 0.5) / BREAK_FRAGMENT_COUNT - 0.5
            spin = BREAK_FRAGMENT_SPIN_DEGREES * (1.0 if index % 2 == 0 else -1.0)
            pieces.append(
                {
                    "index": index,
                    "offset": chord * share,
                    "length": chord * BREAK_FRAGMENT_CHORD_FRACTION,
                    "depth_fraction": BREAK_FRAGMENT_DEPTH_FRACTION,
                    # Outward, plus a lean along the chord away from the middle.
                    "out_speed": BREAK_FRAGMENT_OUT_SPEED * (0.70 + 0.30 * abs(share) * 2.0),
                    "along_speed": BREAK_FRAGMENT_OUT_SPEED * share * 1.10,
                    "spin_degrees": spin,
                    "seconds": BREAK_FRAGMENT_SECONDS,
                }
            )
        out.setdefault(key, []).append({"t": float(event["t"]), "pieces": pieces})
    return out


def passage_responses(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Freshly broken passages a ball actually went through, and when.

    This is the tier the renderer responds to: break, hole, ball through hole,
    the two flanking pillars answer for half a second. It fires twice per run
    on each of the three review candidates, and on 1176 the first of the two is
    the winner's own break-route escape through the final wall - the single
    most important instant in that candidate.

    `flood_through` is the same list filtered to the brief's stronger
    condition, and that one fires nowhere. See its note.
    """
    _require_valid(document)
    breaks: dict[str, float] = {}
    for event in document["events"]:
        if event["kind"] == "panel_break":
            breaks.setdefault(
                _panel_key(event["shell_id"], event["panel_id"]), float(event["t"])
            )
    uses: dict[str, list[dict[str, Any]]] = {}
    for event in document["events"]:
        if event["kind"] != "shell_exit" or event.get("route") != "break":
            continue
        key = _panel_key(event["shell_id"], event["panel_id"])
        uses.setdefault(key, []).append(
            {"t": float(event["t"]), "ball_id": int(event["ball_id"]),
             "team_id": int(event["team_id"])}
        )
    out: list[dict[str, Any]] = []
    for key, at in sorted(breaks.items()):
        window = [
            use for use in uses.get(key, [])
            if at <= use["t"] <= at + FLOOD_WINDOW_SECONDS
        ]
        if not window:
            continue
        shell_id, panel_id = (int(part) for part in key.split(":"))
        teams = sorted({use["team_id"] for use in window})
        out.append(
            {
                "shell_id": shell_id,
                "panel_id": panel_id,
                "break_t": at,
                "first_use_t": window[0]["t"],
                "last_use_t": window[-1]["t"],
                "balls": len(window),
                "ball_ids": [use["ball_id"] for use in window],
                "teams": teams,
                "both_teams": len(teams) > 1,
                "response_until": window[-1]["t"] + FLOOD_RESPONSE_SECONDS,
            }
        )
    out.sort(key=lambda entry: (entry["break_t"], entry["shell_id"], entry["panel_id"]))
    return out


def flood_through(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Passages that *several* balls poured through soon after they opened.

    **This never happens, and the reason is structural rather than a tuning
    miss.** The brief calls it potentially the best moment in the video. The
    detection is exact - a `panel_break` opens a slot and `shell_exit` events
    with `route == "break"` on that same slot are the balls going through it -
    and on 17964, 3762 and 1176 it returns nothing at 1.8 s, nothing at 3.0 s,
    one/none/none at 5.0 s, and two/none/two at 8.0 s.

    Every shell rotates, at 0.27 to 0.77 rad/s. A broken slot is therefore not
    a door, it is a gap sweeping past the population, and by the time a second
    ball is anywhere near it the gap has moved. Ball-ball collisions are off
    and nothing steers, so there is no mechanism that would bring a second ball
    to the same slot in the same second. Measured first-use delays are 0.36 to
    14.44 s and the *second* use, where there is one, is 3.45 to 12.42 s after
    the break.

    The mechanism is kept because it is correct and costs nothing, and because
    a future phase that slowed the outer shells would want it. What the
    renderer actually responds to is `passage_responses`.
    """
    return [
        entry for entry in passage_responses(document)
        if int(entry["balls"]) >= FLOOD_MIN_BALLS
    ]




# --------------------------------------------------------------------------
# Phase 4B: containment, critical visibility, occupancy and frame sizes
# --------------------------------------------------------------------------


def containment_report(document: dict[str, Any], fps: float = 60.0) -> dict[str, Any]:
    """Is every ball inside the framed disc on every rendered frame?

    This is the check that makes "cropping is allowed" safe to say. The brief
    permits outer *geometry* to leave the frame; it does not permit a ball to.
    A grouped camera holds one framing across two frontier regions, so the
    question has teeth for the first time - Phase 4A's per-shell schedule could
    not fail it by construction and therefore never measured it.

    Measured against the **frame rectangle**, not against the framed material
    disc. Those are different numbers once the arena is allowed to cross the
    frame's own edge, and gating on the disc would reject framings that show
    everything, which is the Phase 4A mistake in a new place.

    **4C changes what the answer is allowed to be.** Up to 4B the framed arena
    was narrower than the frame, so "no ball is ever off screen" was free and
    the report only had to confirm it. At `FRONTIER_WIDTH_FRACTION = 1.200` the
    arena is 108 px wider than the half frame on each side by construction, so
    a ball out at a horizontal cap of the outer region *is* off screen and
    saying otherwise would mean giving up the framing the review asked for.

    So the question becomes *when* and *how much*, and the two properties worth
    holding are here as numbers rather than as one boolean:

    * `outside_before_lock` - the camera is still moving then, and a ball
      leaving a frame that is itself moving is the one version of this a viewer
      reads as a mistake. It is 0 on both production candidates.
    * `outside_frames` against `frames` - how often it happens at all, which is
      8.5% and 11.6%, every one of them after the lock.

    What may never happen is a *critical subject* off frame, and that is
    `critical_visibility_report`, which measures the frame edge as well as the
    action rail for exactly this reason.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    ball_radius = float(document["config"]["ball_radius"]) * BALL_DRAW_SCALE
    frames = max(1, int(math.ceil(duration * fps)))
    lock = camera_lock_time(document)
    worst = 0.0
    worst_t = 0.0
    worst_ball = -1
    worst_overshoot_px = 0.0
    outside_frames = 0
    outside_before_lock = 0
    ball_samples = 0
    ball_samples_outside = 0
    for index in range(frames + 1):
        t = duration * index / frames
        view = view_radius_at(document, t)
        scale = pixels_per_unit(view)
        radius_px = ball_radius * scale
        any_out = False
        for ball_id, point in positions_at(document, t).items():
            px, py = project(point, view)
            margin = min(px, FRAME_WIDTH - px, py, FRAME_HEIGHT - py)
            ratio = radius_px / margin if margin > 0.0 else float("inf")
            ball_samples += 1
            if ratio > worst:
                worst, worst_t, worst_ball = ratio, t, int(ball_id)
            if ratio > 1.0:
                any_out = True
                ball_samples_outside += 1
                worst_overshoot_px = max(worst_overshoot_px, radius_px - margin)
        if any_out:
            outside_frames += 1
            if t < lock:
                outside_before_lock += 1
    return {
        "fps": fps,
        "frames": frames + 1,
        "camera_lock_time": lock,
        "worst_ratio": worst,
        "worst_t": worst_t,
        "worst_ball": worst_ball,
        "worst_overshoot_px": worst_overshoot_px,
        "outside_frames": outside_frames,
        "outside_before_lock": outside_before_lock,
        "outside_frame_fraction": outside_frames / float(frames + 1),
        "ball_samples": ball_samples,
        "ball_samples_outside": ball_samples_outside,
        "ball_sample_outside_fraction": (
            ball_samples_outside / float(ball_samples) if ball_samples else 0.0),
        "contained": outside_frames == 0,
        "contained_while_moving": outside_before_lock == 0,
    }


def _critical_subjects(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Every instant at which something specific must be visible, and what.

    Each entry names a canonical event, the instant to check and the world
    point that may not sit behind the player's controls. "The whole arena" is
    deliberately not on this list: the review agreed to spend the outer arc.
    """
    subjects: list[dict[str, Any]] = []
    used_passages: set[tuple[int, int]] = set()
    for event in document["events"]:
        if event["kind"] == "shell_exit" and event.get("route") == "break":
            used_passages.add((int(event["shell_id"]), int(event["panel_id"])))

    first_spawn = True
    for event in document["events"]:
        kind = event["kind"]
        if kind == "ball_spawn" and first_spawn:
            first_spawn = False
            subjects.append({
                "what": "first_clone", "t": float(event["t"]),
                "point": tuple(event["position"]),
                "detail": "ball %d" % int(event["ball_id"]),
            })
        elif kind == "panel_break":
            key = (int(event["shell_id"]), int(event["panel_id"]))
            if key in used_passages:
                subjects.append({
                    "what": "passage_break", "t": float(event["t"]),
                    "point": tuple(event["position"]),
                    "detail": "s%dp%d" % key,
                })
        elif kind == "shell_exit":
            subjects.append({
                "what": "frontier_crossing", "t": float(event["t"]),
                "point": tuple(event["position"]),
                "detail": "%s to region %d" % (event["route"], int(event["to_region"])),
            })
        elif kind == "near_miss" and float(
            event["arc_separation_ball_radii"]
        ) <= STRONG_NEAR_MISS_RADII:
            subjects.append({
                "what": "strong_near_miss", "t": float(event["t"]),
                "point": tuple(event["ball_position"]),
                "detail": "%.2f radii" % float(event["arc_separation_ball_radii"]),
            })
        elif kind == "escape":
            subjects.append({
                "what": "winning_escape", "t": float(event["t"]),
                "point": tuple(event["position"]),
                "detail": "ball %d %s" % (int(event["ball_id"]), event["team_name"]),
            })
    return subjects


#: How much of a critical subject may be covered before it counts as hidden.
CRITICAL_COVER_LIMIT = 0.34

#: The classes that may never be hidden, whatever the framing buys elsewhere.
CRITICAL_HARD_CLASSES: tuple[str, ...] = (
    "winning_escape", "passage_break", "first_clone",
)


def critical_visibility_report(
    document: dict[str, Any], config: SafeAreaConfig = DEFAULT_SAFE_AREA
) -> dict[str, Any]:
    """Event-aware safe area: is the thing the viewer is watching visible?

    Phase 4A asked "does the arena clear the action rail", answered 15.12 px,
    and that single number is what capped the arena at 0.652 of the frame. It
    is the wrong question for a 9:16 arena the viewer never needs to see all
    of. This asks the question the human review actually cares about, once per
    canonical critical instant, and reports the worst.
    """
    _require_valid(document)
    ball_radius = float(document["config"]["ball_radius"]) * BALL_DRAW_SCALE
    rows: list[dict[str, Any]] = []
    for subject in _critical_subjects(document):
        view = view_radius_at(document, float(subject["t"]))
        scale = pixels_per_unit(view)
        px, py = project(subject["point"], view)
        radius_px = ball_radius * scale
        covered = 0.0
        where = ""
        for region in config.regions:
            fraction = _disc_rect_fraction(px, py, radius_px, region)
            if fraction > covered:
                covered, where = fraction, region.name
        # 4C: the frame edge counts too, and it counts the same way. A subject
        # half off the screen is exactly as lost as a subject half under the
        # player's controls, so the two are combined into one "how much of this
        # can the viewer not see" rather than gated separately.
        offframe = _disc_offframe_fraction(px, py, radius_px)
        if offframe > covered:
            covered, where = offframe, "off_frame"
        rows.append({
            "what": subject["what"], "t": float(subject["t"]),
            "detail": subject["detail"], "x_px": px, "y_px": py,
            "radius_px": radius_px, "covered": covered, "region": where,
            "off_frame": offframe,
            "visible": covered < CRITICAL_COVER_LIMIT,
        })
    by_kind: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_kind.setdefault(
            row["what"], {"count": 0, "hidden": 0, "worst_covered": 0.0,
                          "worst_off_frame": 0.0})
        entry["count"] += 1
        entry["hidden"] += 0 if row["visible"] else 1
        entry["worst_covered"] = max(entry["worst_covered"], row["covered"])
        entry["worst_off_frame"] = max(
            entry["worst_off_frame"], row["off_frame"])
    worst = max(rows, key=lambda row: row["covered"]) if rows else None
    return {
        "safe_area": config.name,
        "fingerprint": config.fingerprint(),
        "cover_limit": CRITICAL_COVER_LIMIT,
        "subjects": len(rows),
        "by_kind": by_kind,
        "worst": worst,
        "hidden": [row for row in rows if not row["visible"]],
        "critical_pass": all(
            row["visible"] for row in rows
            if row["what"] in CRITICAL_HARD_CLASSES
        ),
        "hard_on_frame": all(
            row["off_frame"] <= 0.0 for row in rows
            if row["what"] in CRITICAL_HARD_CLASSES
        ),
        "worst_hard_off_frame": max(
            [row["off_frame"] for row in rows
             if row["what"] in CRITICAL_HARD_CLASSES] or [0.0]),
        "pass": all(row["visible"] for row in rows),
    }


def _arc_material_fraction(shell: Mapping[str, Any]) -> float:
    """What share of a shell's circumference is panel rather than opening."""
    count = int(shell["panel_count"])
    open_slots = len(shell["open_slots"])
    return (count - open_slots) / float(count) if count else 0.0


def _ring_frame_clip(outer_px: float) -> float:
    """Roughly what share of a ring of that radius is inside the frame."""
    if outer_px <= 0.0:
        return 1.0
    cx = ARENA_CENTRE_X_FRACTION * FRAME_WIDTH
    cy = ARENA_CENTRE_Y_FRACTION * FRAME_HEIGHT
    inside = 0
    steps = 360
    for index in range(steps):
        angle = 2.0 * math.pi * index / steps
        x = cx + outer_px * math.cos(angle)
        y = cy - outer_px * math.sin(angle)
        if 0.0 <= x <= FRAME_WIDTH and 0.0 <= y <= FRAME_HEIGHT:
            inside += 1
    return inside / float(steps)


def occupancy_at(document: dict[str, Any], t: float) -> dict[str, float]:
    """An analytic estimate of how much of the frame is not empty dark space.

    Not computer vision, as the brief allows, and deliberately not a Monte
    Carlo: every drawn thing here is a disc, an annulus or a ring segment, so
    the areas are closed forms clipped to the frame rectangle. The renderer's
    own frames are measured separately by the laboratory tool, and the two
    agreeing is what makes either of them worth quoting.
    """
    view = view_radius_at(document, t)
    scale = pixels_per_unit(view)
    distance = camera_distance(view)
    frame_area = float(FRAME_WIDTH * FRAME_HEIGHT)

    material = 0.0
    for index, shell in enumerate(document["shells"]):
        radius = float(shell["radius"])
        thickness = float(shell["thickness"])
        depth = float(PANEL_DEPTH[index])
        # The flank a viewer sees is the band between the front silhouette and
        # the back face's projection, which perspective shrinks by d / (D + d).
        flank = radius * depth / (distance + depth)
        outer = (radius + 0.5 * thickness) * scale
        inner = max(0.0, radius - 0.5 * thickness - flank) * scale
        ring = math.pi * (outer * outer - inner * inner)
        material += ring * _arc_material_fraction(shell) * _ring_frame_clip(outer)

    ball_radius_px = float(document["config"]["ball_radius"]) * BALL_DRAW_SCALE * scale
    balls = 0.0
    for point in positions_at(document, t).values():
        px, py = project(point, view)
        if (-ball_radius_px <= px <= FRAME_WIDTH + ball_radius_px
                and -ball_radius_px <= py <= FRAME_HEIGHT + ball_radius_px):
            balls += math.pi * ball_radius_px * ball_radius_px

    footprint = _disc_frame_fraction((view / (1.0 + VIEW_PAD_FRACTION)) * scale)
    return {
        "t": t,
        "material_fraction": material / frame_area,
        "ball_fraction": balls / frame_area,
        "ink_fraction": (material + balls) / frame_area,
        "arena_footprint_fraction": footprint,
        "empty_fraction": 1.0 - (material + balls) / frame_area,
    }


def occupancy_report(document: dict[str, Any], samples: int = 96) -> dict[str, Any]:
    """Early, middle and late occupancy, which is the review's own complaint.

    "Action visually loses intensity while simulation activity is actually
    increasing" is a claim about this number falling while the population
    rises. The thirds are of the playback, so they are comparable between
    candidates without any tuning.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    rows = [
        occupancy_at(document, duration * index / max(1, samples - 1))
        for index in range(samples)
    ]
    keys = ("material_fraction", "ball_fraction", "ink_fraction",
            "arena_footprint_fraction", "empty_fraction")
    thirds: dict[str, dict[str, float]] = {}
    for name, (low, high) in (("early", (0.0, 1.0 / 3.0)),
                              ("middle", (1.0 / 3.0, 2.0 / 3.0)),
                              ("late", (2.0 / 3.0, 1.0))):
        window = [row for row in rows
                  if low * duration <= row["t"] <= high * duration]
        thirds[name] = {
            key: statistics.fmean([row[key] for row in window]) for key in keys
        }
    return {
        "samples": samples,
        "thirds": thirds,
        "late_minus_early_ink": (thirds["late"]["ink_fraction"]
                                 - thirds["early"]["ink_fraction"]),
        "late_not_emptier": (thirds["late"]["ink_fraction"]
                             >= thirds["early"]["ink_fraction"]),
        "min_ink_fraction": min(row["ink_fraction"] for row in rows),
        "max_ink_fraction": max(row["ink_fraction"] for row in rows),
    }


def frame_size_report(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The brief's frame-size table: what things measure, per camera stage."""
    _require_valid(document)
    shells = document["shells"]
    ball_radius = float(document["config"]["ball_radius"])
    rows: list[dict[str, Any]] = []
    for stage in camera_stages(document):
        extent = int(stage["extent_shell"])
        view = float(stage["radius"])
        scale = pixels_per_unit(view)
        distance = camera_distance(view)
        shell = shells[extent]
        radius = float(shell["radius"])
        thickness = float(shell["thickness"])
        depth = float(PANEL_DEPTH[extent])
        gap = min(float(opening["gap_chord"]) for opening in shell["openings"])
        flank = radius * depth / (distance + depth)
        rows.append({
            "stage": int(stage["stage"]),
            "extent_shell": extent,
            "start": float(stage["start"]),
            "settled": float(stage["settled"]),
            "view_radius": view,
            "pixels_per_unit": scale,
            "camera_distance": distance,
            "frontier_diameter_px": 2.0 * (radius + 0.5 * thickness) * scale,
            "ball_diameter_px": 2.0 * ball_radius * scale,
            "ball_drawn_diameter_px": 2.0 * ball_radius * BALL_DRAW_SCALE * scale,
            "opening_width_px": gap * scale,
            "opening_over_ball": gap / (2.0 * ball_radius),
            "wall_face_thickness_px": thickness * scale,
            "wall_apparent_thickness_px": (thickness + flank) * scale,
            "wall_flank_px": flank * scale,
            "occupancy": occupancy_at(document, float(stage["settled"])),
        })
    return rows


# --------------------------------------------------------------------------
# Readability
# --------------------------------------------------------------------------


def readability_report(document: dict[str, Any], fps: float = 30.0) -> dict[str, Any]:
    """Can the viewer follow the balls, and does the population read?

    Four questions, all of them answered from the document and the projection
    rather than from a render, because a number that comes from reading pixels
    back can only be taken after the render and this one has to be able to
    reject a composition before it is made.

    * **Crowding.** With ball-ball collisions off, two balls may occupy the
      same pixel, and at fifteen balls that is the failure mode the brief names
      - a glow cloud. The closest pair is the obvious measure and it is the
      wrong one: two balls crossing for three frames is not a glow cloud, and
      over twenty seconds and fifteen balls a near-coincidence is certain. So
      the report clusters the balls on each frame at a one-diameter threshold
      and asks how many **distinguishable blobs** there are against how many
      balls there are, what the largest cluster gets to, and how long a cluster
      of three or more survives. A three-ball merge that lasts a fifth of a
      second is a glint; one that lasts two seconds is the failure.
    * **Continuity.** How far a ball moves between two frames against its own
      drawn diameter. Above 1.0 the ball strobes and needs the trail to bridge
      it; Test #1 found 2.2 at 30 fps and had to add one.
    * **Escalation.** The population at each third of the run, which is the one
      thing the redesign exists to show.
    * **Team load.** How many of each colour are on screen at once, and how
      often a cluster the eye has to separate contains *both* colours - which
      is the only overlap that can damage the one read the video exists for.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    ball_radius = float(document["config"]["ball_radius"])
    palette = team_palette(document)
    frames = max(2, int(round(duration * fps)))

    closest = math.inf
    closest_t = 0.0
    max_step_ratio = 0.0
    max_step_t = 0.0
    peak_population = 0
    peak_t = 0.0
    max_teams = 0
    max_on_screen_by_team = [0] * len(TEAM_NAMES)
    mixed_cluster_frames = 0
    largest_mixed_cluster = 0
    largest_cluster = 1
    largest_cluster_t = 0.0
    merge_run = 0
    worst_merge_run = 0
    worst_merge_t = 0.0
    blob_deficit_frames = 0
    blob_sum = 0.0
    ball_sum = 0.0
    previous: dict[int, tuple[float, float]] = {}

    for index in range(frames + 1):
        t = duration * index / frames
        view = view_radius_at(document, t)
        scale = pixels_per_unit(view)
        drawn_diameter = 2.0 * ball_radius * BALL_DRAW_SCALE * scale
        points = positions_at(document, t)
        screen = {b: project(p, view) for b, p in points.items()}

        if len(screen) > peak_population:
            peak_population = len(screen)
            peak_t = t
        on_screen = [0] * len(TEAM_NAMES)
        for b in screen:
            on_screen[palette[b]["team"]] += 1
        max_teams = max(max_teams, sum(1 for c in on_screen if c))
        for index, count in enumerate(on_screen):
            max_on_screen_by_team[index] = max(max_on_screen_by_team[index], count)

        ids = sorted(screen)
        # Union-find over "centres closer than one drawn diameter". A component
        # is what the eye has to separate; its size is what makes that hard.
        parent = {ball_id: ball_id for ball_id in ids}

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                ax, ay = screen[ids[i]]
                bx, by = screen[ids[j]]
                ratio = math.hypot(ax - bx, ay - by) / drawn_diameter
                if ratio < closest:
                    closest = ratio
                    closest_t = t
                if ratio < 1.0:
                    ra, rb = find(ids[i]), find(ids[j])
                    if ra != rb:
                        parent[ra] = rb

        sizes: dict[int, int] = {}
        cluster_teams: dict[int, set[int]] = {}
        for ball_id in ids:
            root = find(ball_id)
            sizes[root] = sizes.get(root, 0) + 1
            cluster_teams.setdefault(root, set()).add(palette[ball_id]["team"])
        biggest = max(sizes.values()) if sizes else 1
        # A cluster holding both colours is the only overlap that can put the
        # video's one question in doubt, so it is counted on its own rather than
        # folded into the cluster-size number.
        mixed = [root for root, seen in cluster_teams.items() if len(seen) > 1]
        if mixed:
            mixed_cluster_frames += 1
            largest_mixed_cluster = max(
                largest_mixed_cluster, max(sizes[root] for root in mixed)
            )
        blobs = len(sizes)
        blob_sum += blobs
        ball_sum += len(ids)
        if blobs < len(ids):
            blob_deficit_frames += 1
        if biggest > largest_cluster:
            largest_cluster = biggest
            largest_cluster_t = t
        if biggest >= 3:
            merge_run += 1
            if merge_run > worst_merge_run:
                worst_merge_run = merge_run
                worst_merge_t = t
        else:
            merge_run = 0

        for ball_id, point in screen.items():
            if ball_id in previous:
                step = math.hypot(point[0] - previous[ball_id][0],
                                  point[1] - previous[ball_id][1])
                ratio = step / drawn_diameter
                if ratio > max_step_ratio:
                    max_step_ratio = ratio
                    max_step_t = t
        previous = screen

    thirds = []
    for third in range(3):
        at = duration * (third + 1) / 3.0
        thirds.append(len(positions_at(document, at)))

    return {
        "fps": fps,
        "peak_population": peak_population,
        "peak_population_t": peak_t,
        "population_by_third": thirds,
        "population_first_frame": len(positions_at(document, 0.0)),
        "teams_on_screen_max": max_teams,
        "max_on_screen_by_team": list(max_on_screen_by_team),
        "mixed_cluster_frames": mixed_cluster_frames,
        "mixed_cluster_fraction": mixed_cluster_frames / float(frames + 1),
        "largest_mixed_cluster": largest_mixed_cluster,
        "closest_pair_diameters": closest if closest < math.inf else None,
        "closest_pair_t": closest_t,
        "largest_cluster": largest_cluster,
        "largest_cluster_t": largest_cluster_t,
        "longest_triple_merge_seconds": worst_merge_run / fps,
        "longest_triple_merge_t": worst_merge_t,
        "blob_deficit_frames": blob_deficit_frames,
        "blob_deficit_fraction": blob_deficit_frames / float(frames + 1),
        "mean_blobs_per_ball": (blob_sum / ball_sum) if ball_sum else 1.0,
        "max_step_diameters": max_step_ratio,
        "max_step_t": max_step_t,
        "strobes": max_step_ratio > 1.0,
    }


def damage_report(document: dict[str, Any], samples: int = 120) -> dict[str, Any]:
    """The wall's own story: how much of it is marked, and how big the marks are.

    The brief asks whether the five states are legible, which is two separate
    facts - that a state is *reached* often enough to be seen at all, and that
    a panel in that state is big enough on screen to read. The second is the
    one a composition can fail, so the panel's drawn face is reported in pixels
    at the framing in force when that panel actually changed state.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    shells = {int(s["shell_id"]): s for s in document["shells"]}

    reached = {state: 0 for state in DAMAGE_STATES[1:]}
    sizes: dict[str, list[float]] = {state: [] for state in DAMAGE_STATES[1:]}
    for entry in document["panel_states"]:
        shell = shells[int(entry["shell_id"])]
        chord = float(shell["chord_length"])
        thickness = float(shell["thickness"])
        for transition in entry["transitions"]:
            state = transition["state"]
            reached[state] = reached.get(state, 0) + 1
            view = view_radius_at(document, float(transition["t"]))
            scale = pixels_per_unit(view)
            sizes[state].append(chord * scale)
        if entry["break_time"] is not None:
            reached["broken"] += 1
            view = view_radius_at(document, float(entry["break_time"]))
            scale = pixels_per_unit(view)
            sizes["broken"].append(chord * scale)
            sizes.setdefault("broken_face_px", []).append(thickness * scale)

    timeline = []
    for index in range(samples + 1):
        t = duration * index / samples
        counts = damage_counts_at(document, t)
        timeline.append({"t": t, **counts})

    end = damage_counts_at(document, duration)
    return {
        "states_reached": reached,
        "panel_chord_px_when_reached": {
            state: {
                "min": min(values),
                "median": sorted(values)[len(values) // 2],
                "max": max(values),
            }
            for state, values in sizes.items()
            if values and state in DAMAGE_STATES
        },
        "final_counts": end,
        "damaged_or_worse_at_end": end["panels"] - end["healthy"],
        "broken_at_end": end["broken"],
        "shared_breaks": sum(
            1
            for event in document["events"]
            if event["kind"] == "panel_break" and int(event["contributors"]) > 1
        ),
        "timeline": timeline,
    }


# --------------------------------------------------------------------------
# The stills the brief asks for
# --------------------------------------------------------------------------

#: The eleven views the Phase 4B contact sheet has to answer for, in order.
#: `c_first_transition` and `h_final_wall` are new because the review's
#: complaints were about the camera and the final wall, and a sheet that never
#: shows either cannot be used to judge whether they were fixed.
#: `g_flood_through` is on the list and is expected to be absent - see
#: `flood_through`.
STILL_ORDER: tuple[str, ...] = (
    "a_opening",
    "b_first_split",
    "c_first_transition",
    "d_four_balls",
    "e_damaged_panel",
    "f_critical_panel",
    "g_panel_break",
    "g2_flood_through",
    "h_final_wall",
    "i_final_escape",
    "j_winner_frame",
)


def event_moments(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The nine named instants, each one an actual canonical event time.

    Chosen rather than sampled: a still of "a panel breaking" taken at a round
    number of seconds is a still of whatever happened to be on screen. Each of
    these is a canonical event plus a stated offset, and the offset is there
    only so the still lands inside the effect rather than on its first frame.
    """
    _require_valid(document)
    duration = float(document["summary"]["duration"])
    events = document["events"]
    balls = {int(b["ball_id"]): b for b in document["balls"]}

    def first(kind: str, predicate=None) -> dict[str, Any] | None:
        for event in events:
            if event["kind"] == kind and (predicate is None or predicate(event)):
                return event
        return None

    def last(kind: str, predicate=None) -> dict[str, Any] | None:
        found = None
        for event in events:
            if event["kind"] == kind and (predicate is None or predicate(event)):
                found = event
        return found

    moments: list[dict[str, Any]] = []

    moments.append({"name": "a_opening", "t": min(0.30, duration), "why": "frame one"})

    stages = camera_stages(document)
    if len(stages) > 1:
        first_move = stages[1]
        moments.append(
            {
                "name": "c_first_transition",
                "t": min(duration, float(first_move["start"])
                         + 0.5 * FRAME_EASE_SECONDS),
                "why": (
                    f"mid-way through the only reframe before the final wall, "
                    f"triggered by the race reaching region "
                    f"{first_move['trigger_region']} at "
                    f"{float(first_move['trigger_t']):.2f}s"
                ),
            }
        )

    spawn = first("ball_spawn")
    if spawn is not None:
        moments.append(
            {
                "name": "b_first_split",
                "t": float(spawn["t"]) + 0.5 * SPAWN_LINK_SECONDS,
                "why": f"ball {spawn['ball_id']} born at {float(spawn['t']):.2f}s",
            }
        )

    fourth = None
    for ball in document["balls"]:
        if int(ball["ball_id"]) == 3:
            fourth = float(ball["birth_time"])
    if fourth is not None:
        moments.append(
            {"name": "d_four_balls", "t": min(duration, fourth + 0.45),
             "why": "0.45 s after the fourth ball exists"}
        )

    # **The final-wall struggle**, which is the view the brief sets a five-part
    # human gate on. Taken at the latest population peak inside the locked
    # final framing, so it is the busiest instant of the hardest section, and
    # clamped before the escape so it cannot show the payoff banner.
    escape_t = float(document["summary"]["escape_time"])
    lock = camera_lock_time(document)
    if lock < escape_t:
        best_t = 0.5 * (lock + escape_t)
        best = -1
        for index in range(41):
            t = lock + (escape_t - lock) * index / 40.0
            alive = len(live_balls_at(document, t))
            if alive > best:
                best, best_t = alive, t
        moments.append(
            {
                "name": "h_final_wall",
                "t": min(escape_t - 0.05, best_t),
                "why": (
                    f"{best} balls against the final wall, "
                    f"{escape_t - lock:.2f}s of locked camera"
                ),
            }
        )

    damaged = first("damage_state", lambda e: e["new_state"] == "damaged")
    if damaged is not None:
        moments.append(
            {"name": "e_damaged_panel", "t": float(damaged["t"]) + 0.35,
             "why": f"shell {damaged['shell_id']} panel {damaged['panel_id']}"}
        )

    # Prefer a fractured panel; a run with none still has criticals.
    worst = first("damage_state", lambda e: e["new_state"] == "fractured")
    if worst is None:
        worst = first("damage_state", lambda e: e["new_state"] == "critical")
    if worst is not None:
        moments.append(
            {"name": "f_critical_panel", "t": float(worst["t"]) + 0.35,
             "why": f"{worst['new_state']} on shell {worst['shell_id']} "
                    f"panel {worst['panel_id']}"}
        )

    # The most interesting break is one more than one ball paid for.
    shared = first("panel_break", lambda e: int(e["contributors"]) > 1)
    if shared is None:
        shared = first("panel_break")
    if shared is not None:
        moments.append(
            {
                "name": "g_panel_break",
                "t": float(shared["t"]) + 0.25 * BREAK_RETRACT_SECONDS,
                "why": (
                    f"shell {shared['shell_id']} panel {shared['panel_id']}, "
                    f"{shared['hits']} hits from {shared['contributors']} balls"
                ),
            }
        )

    # A ball going through a passage it or its team broke open. The brief asks
    # for the stronger version - several balls pouring through at once - and
    # `flood_through` explains at length why no candidate has one. This is the
    # strongest thing that does happen, and on 1176 it is the winning escape.
    passages = passage_responses(document)
    if passages:
        # Most balls wins; then the outermost shell, then the latest break.
        # Ranking by earliest break instead picked 1176's shell-0 passage over
        # its shell-4 one - and the shell-4 one *is* that candidate's winning
        # escape, which is the whole reason 1176 is in the review set.
        best_passage = max(
            passages,
            key=lambda entry: (
                int(entry["balls"]), int(entry["shell_id"]), float(entry["break_t"])
            ),
        )
        moments.append(
            {
                "name": "g2_flood_through",
                "t": min(duration - 0.02, float(best_passage["first_use_t"]) + 0.06),
                "why": (
                    f"{best_passage['balls']} ball(s) through the s"
                    f"{best_passage['shell_id']}p{best_passage['panel_id']} passage "
                    f"{float(best_passage['first_use_t']) - float(best_passage['break_t']):.2f}s "
                    f"after it opened"
                ),
            }
        )

    escape = last("escape")
    if escape is not None:
        moments.append(
            {
                "name": "i_final_escape",
                "t": float(escape["t"]) + 0.45 * ESCAPE_FLARE_SECONDS,
                "why": (
                    f"ball {escape['ball_id']}, generation {escape['generation']}, "
                    f"route {escape['route']}"
                ),
            }
        )
        placement = winner_banner_placement(document)
        moments.append(
            {
                "name": "j_winner_frame",
                "t": float(escape["t"]) + RELEASE_SECONDS * 0.8,
                "why": (
                    f"{placement.get('team_name', '?').upper()} ESCAPES! at "
                    f"{'top' if placement.get('moved_to_top') else 'lower'} third, "
                    f"clear of the ball: {placement.get('clear_of_ball')}"
                ),
            }
        )

    order = {name: index for index, name in enumerate(STILL_ORDER)}
    moments.sort(key=lambda entry: order.get(entry["name"], 99))
    return moments


# --------------------------------------------------------------------------
# One report per candidate
# --------------------------------------------------------------------------


def measure_document(document: dict[str, Any], fps: float = 30.0) -> dict[str, Any]:
    """Everything the brief asks to be measured, for one seed."""
    _require_valid(document)
    composition = composition_report(document)
    # The samples are for a chart nobody is drawing; the report keeps the
    # summary and drops them so a manifest of seven seeds stays readable.
    samples = composition.pop("samples")
    damage = damage_report(document)
    timeline = damage.pop("timeline")
    return {
        "seed": int(document["seed"]),
        "digest": document["digest"],
        "summary": {
            key: document["summary"][key]
            for key in (
                "duration", "escaped", "escape_ball", "escape_time",
                "max_population", "max_generation", "breaks", "near_misses",
                "collisions", "spawns",
            )
        },
        "escape_generation": _escape_generation(document),
        "composition": composition,
        "shells": shell_geometry_report(document),
        "safe_area": safe_area_report(document, fps=fps),
        "readability": readability_report(document, fps=fps),
        "damage": damage,
        "moments": event_moments(document),
        "occupancy_samples": len(samples),
        "damage_samples": len(timeline),
        # --- Phase 4B ---
        "camera": {
            "stages": [dict(stage) for stage in camera_stages(document)],
            "transitions": len(camera_stages(document)) - 1,
            "zoom_ratio": zoom_ratio(document),
            "lock_time": camera_lock_time(document),
            "static_tail_seconds": static_tail_seconds(document),
            "frontier_marks": [list(mark) for mark in frontier_marks(document)],
        },
        "containment": containment_report(document, fps=max(fps, 60.0)),
        "critical_visibility": critical_visibility_report(document),
        "occupancy": occupancy_report(document),
        "frame_sizes": frame_size_report(document),
        "passages": passage_responses(document),
        "flood_through": flood_through(document),
        "winner_banner": winner_banner_placement(document),
        "final_wall_wear": wear_report(document),
    }


def _escape_generation(document: dict[str, Any]) -> int | None:
    for event in reversed(document["events"]):
        if event["kind"] == "escape":
            return int(event["generation"])
    return None


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------


def candidate_seeds(shortlist: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply the hard gates and Phase 3B review selection to the shortlist."""
    low, high = CANDIDATE_RULE["duration_seconds"]
    split_max = CANDIDATE_RULE["first_spawn_seconds_max"]
    pop_low, pop_high = CANDIDATE_RULE["population_total"]
    team_low = CANDIDATE_RULE["min_team_population"]
    # The shortlist is the *pool* and `CANDIDATE_SEEDS` is the review set drawn
    # from it, so the intersection is the contract: a seed that is not eligible
    # cannot be reviewed, and a review seed that has dropped out of the pool
    # disappears here rather than being rendered anyway.
    selected = set(CANDIDATE_SEEDS) & {int(seed) for seed in shortlist["seeds"]}
    kept: list[dict[str, Any]] = []
    for candidate in shortlist["candidates"]:
        if int(candidate["seed"]) not in selected:
            continue
        if candidate["flags"]:
            continue
        if not low <= float(candidate["duration"]) <= high:
            continue
        if float(candidate["first_spawn"]) > split_max:
            continue
        if not pop_low <= int(candidate["population_total"]) <= pop_high:
            continue
        race = candidate["race"]
        if min(race["population_by_team"]) < team_low:
            continue
        kept.append(
            {
                "seed": int(candidate["seed"]),
                "duration": float(candidate["duration"]),
                "first_split": float(candidate["first_spawn"]),
                "population": int(candidate["population_total"]),
                "generations": int(candidate["generations"]),
                "escape_route": candidate["escape_route"],
                "escape_generation": int(candidate["escape_generation"]),
                "escape_by": (
                    "founder" if int(candidate["escape_generation"]) == 0
                    else "descendant"
                ),
                "progression_opening": int(candidate["progression_opening"]),
                "progression_break": int(candidate["progression_break"]),
                "breaks": int(candidate["breaks"]),
                "shared_breaks": int(candidate["shared_breaks"]),
                "near_misses": int(candidate["near_misses"]),
                "escalation": float(candidate["escalation"]["meaningful"]),
                "winner": race["winner_name"],
                "winner_generation": race["winner_generation"],
                "winner_route": race["winner_route"],
                "population_by_team": list(race["population_by_team"]),
                "damage_by_team": list(race["damage_by_team"]),
                "cross_team_breaks": int(race["cross_team_breaks"]),
                "stolen_breaks": int(race["stolen_breaks"]),
                "population_lead_changes": int(race["population_lead_changes"]),
                "frontier_lead_changes": int(race["frontier_lead_changes"]),
                "win_margin_seconds": race["win_margin_seconds"],
                "digest": candidate["digest"],
            }
        )
    order = {seed: index for index, seed in enumerate(CANDIDATE_SEEDS)}
    kept.sort(key=lambda entry: order.get(entry["seed"], len(order)))
    return kept


def candidate_manifest(shortlist: dict[str, Any]) -> dict[str, Any]:
    """The committed manifest: the rule, the seeds, and what they span.

    Audio Phase 2B renders the same list, so the list has to be a file rather
    than a paragraph, and it carries the Phase 1 digests so a seed that has
    silently become a different run fails loudly instead of sounding wrong.
    """
    kept = candidate_seeds(shortlist)
    routes = {"opening": 0, "break": 0}
    who = {"founder": 0, "descendant": 0}
    colours = {name: 0 for name in TEAM_NAMES}
    for entry in kept:
        routes[entry["escape_route"]] += 1
        who[entry["escape_by"]] += 1
        colours[entry["winner"]] += 1
    return {
        "format": 2,
        "phase": "category3-test2-two-team-shell-race/v4a",
        "config_digest": shortlist["config_digest"],
        "expected_config_digest": EXPECTED_CONFIG_DIGEST,
        "shortlist_seeds": list(shortlist["seeds"]),
        "rule": CANDIDATE_RULE,
        "seeds": [entry["seed"] for entry in kept],
        "candidates": kept,
        "coverage": {
            "count": len(kept),
            "escape_route": routes,
            "escaping_ball": who,
            "winning_colour": colours,
            "both_colours_win": all(colours[name] > 0 for name in TEAM_NAMES),
            "population_lead_changes": [
                min(e["population_lead_changes"] for e in kept),
                max(e["population_lead_changes"] for e in kept),
            ],
            "win_margin_seconds": [
                min(e["win_margin_seconds"] for e in kept),
                max(e["win_margin_seconds"] for e in kept),
            ],
            "duration_seconds": [
                min(e["duration"] for e in kept),
                max(e["duration"] for e in kept),
            ],
            "first_split_seconds": [
                min(e["first_split"] for e in kept),
                max(e["first_split"] for e in kept),
            ],
            "population": [
                min(e["population"] for e in kept),
                max(e["population"] for e in kept),
            ],
            "opening_dominant": [
                e["seed"] for e in kept
                if e["progression_opening"] >= 3 * max(1, e["progression_break"])
            ],
            "break_heavy": [
                e["seed"] for e in kept
                if e["progression_break"] >= 0.6 * e["progression_opening"]
            ],
        },
    }


# --------------------------------------------------------------------------
# The render configuration, as one hashable object
# --------------------------------------------------------------------------


def render_config() -> dict[str, Any]:
    """Every number the renderer draws with, in one dictionary.

    Its digest goes in the report and in the manifest. Two renders that print
    the same digest were made by the same look; a change to any constant here
    changes it, which is the only way a still in a report can be tied to the
    settings that produced it after the fact.
    """
    return {
        "format": 1,
        "schema": EXPECTED_SCHEMA_VERSION,
        "config_digest": EXPECTED_CONFIG_DIGEST,
        "frame": [FRAME_WIDTH, FRAME_HEIGHT],
        "view_diameter_fraction": VIEW_DIAMETER_FRACTION,
        "arena_centre": [ARENA_CENTRE_X_FRACTION, ARENA_CENTRE_Y_FRACTION],
        "view_pad_fraction": VIEW_PAD_FRACTION,
        "frontier_width_fraction": FRONTIER_WIDTH_FRACTION,
        "usable_width_fraction": USABLE_WIDTH_FRACTION,
        "camera_hfov_degrees": CAMERA_HFOV_DEGREES,
        "camera_near": CAMERA_NEAR,
        "camera_frustum_size": CAMERA_FRUSTUM_SIZE,
        "camera_frustum_offset": list(CAMERA_FRUSTUM_OFFSET),
        "frame_lead_seconds": FRAME_LEAD_SECONDS,
        "frame_ease_seconds": FRAME_EASE_SECONDS,
        "camera_stage_plan": [list(entry) for entry in CAMERA_STAGE_PLAN],
        "event_guard": [
            EVENT_GUARD_BEFORE_SECONDS, EVENT_GUARD_AFTER_SECONDS,
            EVENT_GUARD_MAX_DEFER_SECONDS, STRONG_NEAR_MISS_RADII,
        ],
        "ball_draw_scale": BALL_DRAW_SCALE,
        "halo_scale": HALO_SCALE,
        "ball_rim": [BALL_RIM_SCALE, BALL_RIM_Z],
        "layer_z": [TRAIL_Z, HALO_Z, EFFECT_Z],
        "trail_width": [TRAIL_HEAD_WIDTH, TRAIL_TAIL_WIDTH],
        "trail_seconds": TRAIL_SECONDS,
        "trail_samples": TRAIL_SAMPLES,
        "panel_depth": list(PANEL_DEPTH),
        "post_depth_factor": POST_DEPTH_FACTOR,
        "panel_chamfer": PANEL_CHAMFER,
        "panel_segments": PANEL_SEGMENTS,
        "shell_albedo_value": list(SHELL_ALBEDO_VALUE),
        "shell_metallic": list(SHELL_METALLIC),
        "shell_roughness": list(SHELL_ROUGHNESS),
        "damage_emission_energy": list(DAMAGE_EMISSION_ENERGY),
        "damage_crack_count": list(DAMAGE_CRACK_COUNT),
        "damage_rim": [list(DAMAGE_RIM_RGB), DAMAGE_RIM_ENERGY,
                       DAMAGE_RIM_MARGIN, DAMAGE_RIM_SPAN],
        "damage_seam": [list(DAMAGE_SEAM_STATES), DAMAGE_SEAM_WIDTH,
                        DAMAGE_SEAM_MIN_CHORD],
        "damage_roughness": [DAMAGE_WEAR_ROUGHNESS,
                             list(DAMAGE_STATE_ROUGHNESS)],
        "fracture_segment_recess": list(FRACTURE_SEGMENT_RECESS),
        "damage_team_tint": [DAMAGE_TEAM_TINT, DAMAGE_TEAM_TINT_MIN_SHARE],
        "damage_mark_chord": DAMAGE_MARK_CHORD,
        "damage_chip": [list(DAMAGE_CHIP_RGB), DAMAGE_CHIP_DEPTH],
        "damage_wear": [
            DAMAGE_WEAR_FLOOR, DAMAGE_WEAR_FACE_LOSS, DAMAGE_WEAR_CHIP_SCALE,
        ],
        "damage_cluster": [
            DAMAGE_CLUSTER_CHORD, DAMAGE_CLUSTER_GROWTH, DAMAGE_CLUSTER_GROWTH_MAX,
        ],
        "damage_crack": [
            DAMAGE_CRACK_SPAN, DAMAGE_CRACK_WIDTH, DAMAGE_CRACK_TILT_DEGREES,
        ],
        "damage_branch": [
            list(DAMAGE_BRANCH_COUNT), DAMAGE_BRANCH_SPREAD_DEGREES,
            DAMAGE_BRANCH_LENGTH,
        ],
        "panel_chamfer_by_shell": list(PANEL_CHAMFER_BY_SHELL),
        "fracture": [FRACTURE_GAP, FRACTURE_TILT_DEGREES, FRACTURE_RECESS],
        "spawn": [SPAWN_FLASH_SECONDS, SPAWN_FLASH_RADIUS, SPAWN_LINK_SECONDS],
        "near_miss_seconds": NEAR_MISS_SECONDS,
        "break": [
            BREAK_FLASH_SECONDS, BREAK_RETRACT_SECONDS, BREAK_DEBRIS_SECONDS,
            BREAK_DEBRIS_COUNT, BREAK_RING_SECONDS, BREAK_RING_RADIUS,
        ],
        "break_stress_seconds": BREAK_STRESS_SECONDS,
        "fragments": [
            BREAK_FRAGMENT_COUNT, BREAK_FRAGMENT_SECONDS,
            BREAK_FRAGMENT_CHORD_FRACTION, BREAK_FRAGMENT_DEPTH_FRACTION,
            BREAK_FRAGMENT_OUT_SPEED, BREAK_FRAGMENT_SPIN_DEGREES,
        ],
        "flood": [
            FLOOD_WINDOW_SECONDS, FLOOD_MIN_BALLS, FLOOD_RESPONSE_SECONDS,
            FLOOD_POST_ENERGY,
        ],
        "hook": [
            HOOK_HOLD_SECONDS, HOOK_FADE_SECONDS, HOOK_FADE_TO,
            HOOK_TOP_FRACTION, HOOK_SIZE_FRACTION,
        ],
        "winner": [
            WINNER_SIZE_FRACTION, WINNER_TOP_FRACTION, WINNER_ALT_TOP_FRACTION,
            WINNER_RISE_SECONDS, WINNER_BAND_FRACTION,
        ],
        "escape": [ESCAPE_FLARE_SECONDS, ESCAPE_RING_SECONDS],
        "ending": [RELEASE_SECONDS, END_HOLD_SECONDS],
        "background": list(BACKGROUND_RGB),
        "floor": list(FLOOR_RGB),
        "teams": [list(rgb) for rgb in TEAM_RGB],
        "team_names": list(TEAM_NAMES),
        "generation": [
            GENERATION_WHITEN, GENERATION_WHITEN_MAX, GENERATION_ENERGY_STEP,
            GENERATION_ENERGY_MAX,
        ],
        "panel": list(PANEL_RGB),
        "face": [list(FACE_RGB), FACE_ENERGY],
        "back": [list(BACK_RGB), BACK_ENERGY],
        "post": [
            list(POST_RGB), list(POST_HOT_RGB), list(POST_EDGE_RGB),
            POST_EDGE_ENERGY, POST_BASE_ENERGY, POST_EDGE_DEPTH,
        ],
        "backdrop": [BACKDROP_Z, GLOW_POOL_Z, GLOW_POOL_RADII, GLOW_POOL_ALPHA],
        "debris": [
            BREAK_DEBRIS_SIZE, BREAK_DEBRIS_SPEED, BREAK_DEBRIS_SPEED_SPREAD,
        ],
        "damage_colours": [
            list(CRACK_RGB), list(CRITICAL_RGB), list(FRACTURE_RGB),
            list(BREAK_FLASH_RGB),
        ],
        "safe_area": DEFAULT_SAFE_AREA.fingerprint(),
    }


def render_config_digest() -> str:
    blob = json.dumps(render_config(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

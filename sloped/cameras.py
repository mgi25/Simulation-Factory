"""Cameras cut from the race, in Python, so they can be argued with.

Section 34 of the brief: the layout proof's cameras are blocking cameras. They
aim at fixed points on an empty course, which is the right thing for a shape
competition and the wrong thing for a race. These aim at the marbles.

## Why the camera is solved here and not in GDScript

Everything a camera needs to know is a fact about the replay - where the pack
is, who is leading, when the leader reaches the spinner corridor, when the
first marble crosses the line - and all of it is arithmetic over 800-odd
frames. Done in Python it is testable, diffable and reproducible; done in
GDScript it is only watchable. So this module produces a **camera track**: a
position, an aim point and a field of view per frame per cut, in layout units,
and `sloped_race_scene.gd` sets them and does nothing else.

That also means a camera can be *placed* against the terrain and checked
before anything is rendered. `sloped.terrain` is the mountain, ported exactly -
396 sample points agree with the running scene to 1.7e-5 - and two things here
use it.

**Which side to stand on.** The layout proof's rule, and the reason it exists:
the track's own left is uphill on a leg running one way and downhill on the leg
running back, so a side-on bearing is a tracking shot on one and a camera buried
in the hill on the next. Both candidates are probed nine units out and the one
over lower ground wins - which is also the right answer artistically, because
the open side is the side with the view.

**Whether the shot is clear.** The sight line from the camera to its aim is
walked and the ground checked under it. If the mountain crosses it the elevation
is raised, two degrees at a time, until it does not. The first camera pass
without this put the near hillside across the bottom half of the spinner
corridor shot; with it, the lift each cut needed is a number in the track.

## Sections, from the leader's own progress

The cut boundaries are the times the leader passes each station, not fixed
fractions of the clock: a race whose field jams for two seconds at the fork
should not cut away from the fork on schedule. Progress is arc length along the
route a marble is actually on - the same measure `sloped.race` ranks with - and
it is recomputed here from the replay's positions rather than read from the
summary, because the summary has one number per marble and a camera needs one
per frame.

## Targeting

Four rules, and the choice per cut is the whole of section 36:

* `pack` - the centroid of every marble within `band` of the leader. A leader
  that has broken away is followed by a camera that still has the race in
  frame, because the band is in *route* units and the centroid moves back when
  the field spreads.
* `leader` - the front marble alone. Used only where the front is the story.
* `pair` - the midpoint of the leading two, which is what a finish is.
* `node` - a fixed station, for the establishing shot and the start grid, where
  the marbles have not moved yet and the subject is the machine.

Every track is smoothed with a symmetric moving average before it is written,
because a centroid of eight marbles crossing a mixer is not a smooth curve and
a camera that follows it exactly is a camera nobody can watch.
"""

from __future__ import annotations

import json
import math
import dataclasses
from dataclasses import dataclass, field
from typing import Any, Sequence

from sloped import joins, layout, terrain
from sloped.race import ROUTE_RUNS
from sloped.scale import SIM_TO_LAYOUT

__all__ = [
    "Cut",
    "SECTIONS",
    "STATIONS",
    "progress_track",
    "build_track",
    "write_track",
    "check_track",
    "frame_report",
]


# Where the leader has to get to for each cut to end, as a run and a fraction
# along it. Read as a list of stations rather than of times.
STATIONS = {
    "grid": ("launch", 0.02),
    "launched": ("launch", 0.62),
    "mixed": ("leg1", 0.22),
    "leg1_apex": ("leg1", 0.62),
    "leg2_start": ("leg2", 0.12),
    "obstacle": ("leg2", 0.62),
    "sweep": ("leg3", 0.20),
    "promontory": ("leg3", 0.72),
    "branch_in": ("blue", 0.20),
    "branch_out": ("blue", 0.80),
    "sprint": ("final", 0.40),
    "line": ("final", 1.0),
}


@dataclass
class Cut:
    """One shot: a lens, a targeting rule and the window it covers."""

    name: str
    until: str                    # the station the leader reaches to end it
    fov: float
    extent: float                 # how much of the course to fit, layout units
    elevation: float              # degrees above the horizon
    bearing: float                # degrees from the track's forward at the aim
    target: str = "pack"
    band: float = 60.0            # route units behind the leader, for `pack`
    node: str = ""                # for `target = "node"`
    # Which side of the track the bearing swings toward. Zero asks the terrain,
    # per frame, which is what every cut before V19 did and what all of them
    # keep doing; +1 and -1 fix it to one perpendicular for the whole shot.
    #
    # **A per-frame answer is a per-frame decision, and a decision can change
    # its mind mid-shot.** `terrain.lower_side` probes nine units either side of
    # the aim and takes the lower ground, and where the two are within a metre
    # of each other that verdict flips. On the run-out it does: measured along
    # `final`, the side is (-0.35, +0.94) for a hundred samples and (+0.36,
    # -0.94) from sample 105 on, because the sprint arrives at the finish mesa
    # and the deck's own ground comes up on one side of it. V18's finish crossed
    # that boundary at replay 21.367 s and the camera moved **7.385 layout units
    # in a single frame** - a cut in the middle of a shot - and it landed the
    # lens inside `orange`'s channel, where it stayed to the end.
    #
    # Nothing here detects a flip and smooths it. A shot that needs smoothing is
    # a shot standing where the ground cannot decide, and the fix is to say
    # which side the camera is on.
    side: int = 0
    orbit: tuple[float, float] = (0.0, 0.0)     # degrees of azimuth drift
    dolly: tuple[float, float] = (0.0, 0.0)     # fraction of distance
    hold: float = 0.0             # extra seconds after the station is reached
    min_seconds: float = 0.6
    max_seconds: float = 0.0      # 0 for no cap

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "until": self.until,
            "fov": self.fov,
            "extent": self.extent,
            "elevation": self.elevation,
            "bearing": self.bearing,
            "target": self.target,
            "band": self.band,
            "node": self.node,
            "side": self.side,
        }


# The sequence: eleven cuts, the eight sections section 35 names plus a
# three-quarter-second establishing frame that section 39 allows and caps, plus
# separate shots for the long straight and the branch lobe because on a course
# this long they are two different pieces of racing.
#
# `min_seconds` is not decoration. The course is fast at the top - the leader
# covers the launch and a fifth of leg1 in three seconds - so cuts driven purely
# by station times came out at 0.6 seconds each up there, which reads as a
# glitch rather than as a shot.
#
# The bearings are the one thing here that is a *style* decision rather than an
# arithmetic one, and they follow section 38: a close three-quarter view for the
# grid, a low side follow down the first descent, an outside tracking shot
# through the fast bends, a high compression view over the hairpin, tight on the
# spinners, wide and elevated over the split so both routes are in frame,
# facing the convergence at the merge, low behind the sprint, and a warm
# push-in at the line. Bearing is measured from the track's own forward
# direction at the aim point, so 0 looks back up the course at the field coming
# on, 90 is side-on and 180 follows from behind - and its *side* is chosen by
# the ground rather than by its sign, so a bearing of 62 is a front-quarter view
# from whichever side of the track is downhill there.
#
# Three of the eleven were re-lensed against the terrain rather than by eye,
# because the check said so: `long` at a bearing of 150 puts the camera up-course
# and therefore uphill, and no elevation up to 46 degrees clears the flank - at
# 62 it clears by 1.5 units with no lift at all. `branch` at 142 was the same
# problem on the western lobe. And `establish` at an extent of 150 stood 280
# units out and needed 12 degrees of lift to see over the massif; at 110 it
# stands at 205 and clears on its own.
# ## Why most of these bearings are near zero or near 180
#
# The delivery frame is 1080x1920. A course that is a two-unit ribbon on a
# 78-unit hillside crossing that frame horizontally occupies a band across the
# middle and leaves the top and bottom thirds as unlit mountain - and the first
# full-resolution pass produced exactly that in four of the nine stills, while
# the four that read well were, without this having been noticed, the four
# aimed nearly along the track: 28, 44, 6 and 155 degrees. Looking along the
# channel puts the ribbon receding up the frame, which is the one direction a
# portrait frame has to spare, and it puts the field in depth rather than in a
# line across the middle.
#
# There is a second reason, found later and stronger than the first: a racer
# sits in a cradle 1.4 marble diameters below the top of the channel's outer
# acrylic guard. A camera looking *across* a leg therefore has that guard
# between it and the field, at any elevation - raising it only changes how much
# of the wall the marbles are seen through. Looking along the channel, or down
# it from ahead, is the only bearing from which the cradle is open to the lens.
#
# In the end no cut kept a side-on bearing. `long` was held back at 62 degrees
# on the argument that leg 1's apex is where the course's own zig-zag is
# legible and that wants the turn seen from outside it; the terrain check
# settled it - see the note on that cut.
SECTIONS: tuple[Cut, ...] = (
    Cut("establish", "grid", fov=30.0, extent=110.0, elevation=30.0, bearing=200.0,
        target="node", node="hero", orbit=(-2.0, 2.0), min_seconds=0.75,
        # Section 39 allows half a second to a second of establishing view and
        # then wants the camera on the racers. Capped rather than left to the
        # station, which the leader does not reach until 1.9 s because the fan
        # takes a second and a half to deliver the field to the launch.
        max_seconds=0.95),
    # **Extent 14 rather than 9.5, because the start is a machine now.** The
    # V1 fan pod this lens was framed on was a shelf; the module the physics
    # runs is a mixing drum with a 2.7 wall on a 2.9 catch cone, over a pan
    # that reaches 4.6 back - about 14 layout units end to end. At 9.5 the
    # camera stands inside it.
    Cut("start", "launched", fov=34.0, extent=14.0, elevation=16.0, bearing=28.0,
        target="node", node="start", orbit=(-6.0, 4.0), dolly=(0.10, -0.06),
        min_seconds=1.4),
    # Wider and higher than a low side follow would be, because at an extent of
    # 9 and 9 degrees this shot looks straight through the mixer's housing - the
    # pack is *at* the mixer by the end of the cut and the housing is 3.1 units
    # across in front of it. Raised again, and swung further behind the field,
    # after the first full-resolution pass: at 20 degrees and 104 the channel
    # crosses the frame as a thin band with the housing as the only mass in it,
    # and the racers sit in a cradle whose guard stands 1.4 diameters above
    # them. Looking down the descent rather than across it puts the track on a
    # diagonal and the field on its floor.
    Cut("descent", "mixed", fov=36.0, extent=20.0, elevation=24.0, bearing=160.0,
        target="pack", band=26.0, orbit=(4.0, -4.0), min_seconds=1.0),
    # The last exception to the rule above, and the terrain took it away. Leg
    # 1's apex is on the inside of the zig and therefore uphill, and 62 degrees
    # cleared the flank by 1.5 units with no lift - on one particular field. On
    # another the aim sat a little further round the apex and the ground
    # crossed the sight line by 3.51 units at *46* degrees of elevation, which
    # is the ceiling: there is no camera on that bearing, at any height short
    # of a plan view, that can see the shot. The zig-zag is legible from ahead
    # too, and from ahead the cradle is open to the lens.
    #
    # That reading was half right. Swinging the bearing did not help either,
    # and the real fault was the aim - see `_on_course`. With the aim on the
    # racing line this cut clears the ground by 2.34 units at no lift at all,
    # and the extent is 20 rather than 13 because it is the widest-spread the
    # field ever is: at 13 it held one racer of eight.
    Cut("long", "leg1_apex", fov=36.0, extent=20.0, elevation=18.0, bearing=22.0,
        target="pack", band=44.0, dolly=(0.04, -0.04), min_seconds=1.2),
    # An extent of 13 held two of the eight racers in frame - measured, not
    # judged, by `frame_report`. The field is spread over most of a 44-unit band
    # by the second turn and a hairpin is a shape that has to be read whole, so
    # the extent is the turn's own width and the elevation is enough to see both
    # legs of it at once.
    Cut("hairpin", "leg2_start", fov=34.0, extent=24.0, elevation=34.0, bearing=20.0,
        target="pack", band=44.0, orbit=(-7.0, 5.0), min_seconds=1.0),
    # The last of the side-on bearings to go, and the one that showed what the
    # rule above is really about. At 118 degrees this shot needed 24 degrees of
    # lift to clear the flank it was looking across, which stood it 35 degrees
    # up; and at 150 - along the track, but from behind and above - it still
    # needed the same lift, and the render showed why the frustum count of
    # seven racers in frame meant nothing: they were behind the channel's outer
    # acrylic guard, dimmed and smeared through it. A marble sits in a cradle
    # 1.4 diameters below the guard's top edge, so any camera looking *across*
    # a leg has that wall in the way however high it goes.
    #
    # From ahead, at 30 degrees, the sight line runs down the slope instead of
    # into it - no lift at all - and the field comes over the near lip toward
    # the lens with the cradle open to it. Eight racers in frame and seven
    # legible. `merge` at 6 degrees works for exactly this reason.
    Cut("straight", "obstacle", fov=36.0, extent=14.0, elevation=16.0, bearing=30.0,
        target="pack", band=52.0, dolly=(0.06, -0.05), min_seconds=1.2),
    Cut("obstacle", "sweep", fov=32.0, extent=8.0, elevation=15.0, bearing=44.0,
        target="pack", band=24.0, orbit=(-8.0, 5.0), hold=0.25, min_seconds=1.0),
    # This was aimed at the authored split node, on the argument that the
    # subject of the frame is the fork itself. The frame disagreed: a fixed aim
    # on a moving field put the nearest racer 10.5 units off the aim point, and
    # the still came out a picture of two empty gantries with one marble in it
    # at 42 pixels. The junction is what the *station* is for - the promontory
    # stands off the fork - so the aim goes back on the pack, and the fork is in
    # shot because that is where the pack is.
    # The band is the widest of any cut for a reason particular to this one:
    # a pack aim is the centroid of the racers within the band of the leader,
    # and at the fork the field is at its most strung out, so at 40 units a
    # racer crossing the band edge moved the aim 0.80 units - 1.4 diameters -
    # in a single frame, which `check_track` reports as an aim that snaps. At
    # 56 the whole field is inside it and there is no membership to change.
    # **V1.15 widened the last three pack cuts, because the field is now on two
    # lobes and they are about thirty layout units apart.** Every extent in this
    # list was set against a blue-only race, where the pack is one line in one
    # channel; with orange live, `frame_report` on the selected seed held 4, 2
    # and 3 racers of eight here. Measured across five candidate replays, the
    # widest the pack itself spans during each cut is:
    #
    #     cut       5432   5558   5585   5488   5007   old extent
    #     split     31.8   26.5   28.7   26.4   25.7         16.0
    #     branch    30.6   34.6   35.7   24.3   18.6         19.0
    #     merge     33.0   35.8   34.6   21.3   25.1         15.0
    #
    # so each is framed at roughly half the width its own subject occupies.
    # The new extents are the **median** of those five rather than the largest,
    # so they are sized to the two-lobe field rather than fitted to the seed
    # that ships. The same argument as `hairpin`'s, which is already in this
    # file: "a hairpin is a shape that has to be read whole, so the extent is
    # the turn's own width".
    # **`hold` is V1.15's, and it is where the fork actually happens.** The cut
    # ends at `promontory`, leg3 at 0.72, and the fork's own window is leg3
    # samples 81 to 92 of 118 - 0.69 to 0.78 - so the leader crosses the
    # divider within a tenth of a second of the boundary and the crossing
    # landed in the *next* cut's opening frames. Reviewed against the rendered
    # frames, `split_a`, `split_b` and `split_c` all show one undivided channel
    # with the fork gantry at the frame edge: a viewer sees the approach to a
    # choice and never the choice.
    #
    # **0.3 is the most hold that costs nothing, and that is measured rather
    # than chosen.** Swept against `frame_report` over three replays, total
    # racers in frame across every cut:
    #
    #     hold   0.0   0.3   0.5   0.7   0.9
    #     total  215   215   214   210   203
    #
    # Past 0.3 the cut runs into the divergence itself, where the pack aim sits
    # between two lobes and drops racers out of both - at 0.9 `split` holds
    # three of eight instead of seven. So this buys a third of a second more of
    # the divider at no cost and **does not fully solve branch-choice
    # readability**; the crossing itself is still mostly the `branch` cut's.
    # **V1.17 aims this at the fork and holds it over the whole decision.**
    #
    # A pack aim could not show the choice. The pack is the centroid of the
    # racers within the band, and at the fork the field is at its most strung
    # out, so the aim is always somewhere between marbles and never on the
    # divider; and when the leader crosses to orange, the aim steps to the
    # other lobe. Held longer it got worse rather than better - swept against
    # `frame_report`, racers in frame across every cut went 215, 215, 214, 210,
    # 203 at holds of 0.0 to 0.9 - because the shot was following a point
    # between two diverging lines.
    #
    # A **fixed aim on the fork itself** has none of that. It cannot drift, it
    # cannot step between lobes, and the subject is the one thing that has to
    # be legible here: leg3 arriving, the divider, and both mouths leaving it.
    # The earlier note against a fixed aim - "a picture of two empty gantries
    # with one marble in it at 42 pixels" - was written when the aim was the
    # *authored* `split` node, which is 10.9 units past the divider with
    # orange's lead already gone, and when the course was blue-only so there
    # was never a second stream to see.
    #
    # The hold carries the cut to the point where both routes are in use. On
    # the selected seed the first racer takes orange at 16.07 s and the first
    # takes blue at 17.17 s, so a cut that ends at the station leaves the
    # second half of the decision to the next shot.
    Cut("split", "promontory", fov=34.0, extent=30.0, elevation=38.0, bearing=0.0,
        target="node", node="fork", orbit=(6.0, -6.0), hold=1.6, min_seconds=1.4),
    # Higher, for the same reason as `descent`: at 15 degrees the sprint's own
    # guard rail stood between the camera and the five racers the frustum
    # arithmetic said were in frame, and the still came out empty. Closing in as
    # well - the obvious second move - was measurably worse rather than better:
    # at an extent of 14 the field, which is spread over most of a 48-unit band
    # by the last sprint, went from five racers in frame to one. Elevation was
    # the whole of the fix and extent was none of it.
    Cut("branch", "branch_out", fov=36.0, extent=31.0, elevation=22.0, bearing=152.0,
        target="pack", band=48.0, dolly=(0.05, -0.05), min_seconds=1.4),
    Cut("merge", "sprint", fov=34.0, extent=32.0, elevation=24.0, bearing=6.0,
        target="pack", band=44.0, dolly=(0.05, -0.05), min_seconds=1.2),
    # **Widened from 15 in V1.15, because the win was at the frame edge.** The
    # aim is the midpoint of the leading two and on the selected seed they run
    # 5.3 layout units apart, so each sits 2.65 off the aim - and the delivery
    # frame is portrait. At `fov` 36 *vertical* and 1080x1920 the horizontal
    # field is only 2*atan(tan(18 deg) * 1080/1920) = 20.7 degrees, so an
    # extent of 15 is 15 units tall and **8.4 wide**. The pair plus the line
    # does not fit in 8.4, and the rendered frame at the winning moment has the
    # leader mid-frame with the finish deck at the corner. At 24 the horizontal
    # field is 13.5 units, which holds the pair and the line they are crossing.
    Cut("finish", "line", fov=36.0, extent=24.0, elevation=20.0, bearing=155.0,
        target="pair", orbit=(-4.0, 3.0), dolly=(0.14, -0.10), hold=1.7,
        min_seconds=1.6),
)

# --- the edit ---------------------------------------------------------------
#
# **A cut list is not an edit.** `SECTIONS` tiles the whole replay: every second
# the physics ran is a second of video, and the only editorial decision left is
# which lens is on. That is the right thing for a proof and the wrong thing for
# a film - the selected race spends three and a half seconds mixing eight
# marbles in a drum, which is a mechanism worth one look and not worth a fifth
# of the running time.
#
# An edit is a list of `(lens, replay from, replay to)`, optionally with lens
# overrides, and the windows need not touch. Output time runs at **slope one**
# through every one of them, so a jump between two windows omits replay time
# without altering any marble's speed: nothing here can make the physics look
# faster or slower than it was, only shorter.
#
# The same lens may appear twice. V18's opening does exactly that - the start
# lens holds the eight racers on the line, the edit cuts three and three
# quarter seconds of mixing, and the same lens picks the drum up again as the
# trapdoor goes.
EDIT_V18: tuple[tuple, ...] = (
    # **No establishing shot.** It was 0.95 s of a course 205 units away with
    # the field 14 pixels across, which is a title card rather than a race.
    # Open on the eight racers instead.
    ("start", 0.20, 2.30, {}),
    # The cut. `ShuffleFloor` mixes from 1.6 s to 4.6 s and settles to 5.8;
    # this drops 3.55 s of it and returns just before the floor opens at 6.10.
    ("start", 5.70, 7.62, {}),
    ("descent", 7.62, 8.62, {}),
    ("long", 8.62, 9.80, {}),
    ("hairpin", 9.80, 10.80, {}),
    ("straight", 10.80, 12.00, {}),
    # The spinner corridor ran 3.37 s and is the busiest thing on the course;
    # 2.30 is enough to read it.
    ("obstacle", 12.00, 14.50, {}),
    # V17's fork shot, unchanged: a fixed aim on the divider held over both of
    # this seed's decisions - orange at 16.07 s and blue at 17.17 s.
    ("split", 15.35, 17.67, {}),
    ("branch", 17.67, 19.07, {}),
    ("merge", 19.07, 20.20, {}),
    # **The finish, rebuilt.** V17 framed the leading pair at an extent of 24
    # because the pair straddles 5.3 layout units and a portrait frame is
    # narrow - correct, and it made the marbles small and the line distant. The
    # answer is not a wider lens but a lower, closer one almost directly
    # behind: at a bearing of 170 the sprint recedes up the frame, which is the
    # one direction a 1080x1920 frame has to spare, so the pair and the line
    # they are running at both fit across 13 units instead of 24.
    #
    # It starts before the leader arrives and ends 0.75 s after the fifth
    # racer, so the 0.283 s between first and second and the 0.017 s between
    # fourth and fifth are both in the shot.
    ("finish", 20.20, 23.60, {
        "extent": 13.0,
        "elevation": 12.0,
        "bearing": 170.0,
        "orbit": (-2.0, 2.0),
        "dolly": (0.06, -0.05),
    }),
)

# V19 is V18's edit with one shot re-lensed. **Every window is byte-identical**
# - the same eleven entries, the same replay bounds, the same two cuts, so the
# output clock is unchanged to the frame and nothing before 15.75 s can differ.
# Only the finish's lens is new.
#
# ## What was wrong with V18's finish, measured
#
# It was placed twenty layout units behind the leading pair at twelve degrees,
# and *twenty units behind this finish line is not open air*. The course doubles
# back: the sprint runs out to the line at (19.80, 1.02, 44.40) while `orange`
# comes down the other way just above and behind it, ending at (1.10, 4.90,
# 36.05) beside the sprint's own start. Sampled against the drawn course by
# `sloped.sightlines`, the V18 finish camera stood
#
#     output  lens to nearest surface   sight line to its own aim
#      16.50           3.15 (blue)      clear
#      16.75           2.39 (merge)     clear
#      17.00           0.47 (merge)     BLOCKED by orange 2.43 units out
#      17.50           0.15 (orange)    BLOCKED by orange 2.09 units out
#      19.15           0.37 (orange)    BLOCKED by orange 0.54 units out
#
# which is the review's "at approximately 16.9 s onward the camera becomes
# occluded", found by arithmetic rather than by eye. **0.15 layout units is a
# quarter of a marble's diameter**: the lens was inside the channel's skin.
#
# The trigger is `terrain.lower_side`, which was asked per frame which side of
# the track to stand on and changed its answer at `final[105]` where the sprint
# reaches the finish mesa. The camera moved **7.385 layout units in one frame**
# at replay 21.367 - output 16.92 - and landed on the side `orange` occupies.
# `Cut.side` exists so this shot never asks.
#
# ## The new lens, and the three numbers that fix it
#
# An outside, elevated three-quarter from **downstream**, looking back up the
# sprint at the field coming on, with the deck and its gantry between the lens
# and the mountain rather than a channel between the lens and the racers.
#
# **The aim is the line, not the pair.** `target = "pair"` ranks by progress
# along the route, and a marble that has crossed is rolling out across a deck
# that is not on the route - so on this seed the finish cut's subject came out
# marbles 2 and 7, which are *second and third*. The winner had already crossed
# at the cut's midpoint and was no longer, by that measure, in front. A finish
# does not need following: the racers come to the line, so the line is the aim.
# See `nodes["finish_line"]`.
#
# **Elevation 43, and 40 is a floor the geometry sets.** The FINISH gantry
# carries a 5.4-unit sign whose bottom edge stands 3.26 above the deck, four
# units up-course of the deck's centre - directly between a downstream lens and
# a racer still short of the line. At the winner's crossing the second-placed
# marble is 5.22 units back, and swept across every bearing from 20 to 35 on
# both sides, the sign is across it at **every elevation below 40 degrees**. At
# 43 there is three degrees of margin under the sign and three under this file's
# own 46-degree ceiling, rather than a shot sitting on either limit.
#
# **Side -1, bearing 25.** Of the bearings that clear the gantry, 20-28 on the
# far side is the band that never empties: a racer is in frame in **all 205
# frames** of the shot. The lens stands 14.2 to 17.6 layout units off the
# nearest surface throughout against V18's 0.15, and moves at most 0.06 units a
# frame against V18's 7.385.
#
# **Extent 16, and the contact sheet is what set it.** Every one of 14, 16, 17,
# 18 and 20 passes `sightlines.check_shot` with no findings, so the arithmetic
# had nothing left to say and the frames were rendered and looked at. At 14 the
# FINISH sign - which stands *at* the aim, 3.8 units of gantry on a 14-unit
# frame - takes a third of the picture and the racers are crowded onto the
# bottom edge; at 20 the arena reads but the marbles are barely larger than
# V17's. 16 is where the sprint still arrives from the top of the frame, the
# gantry is a band across the middle rather than the subject, and the deck and
# its catch lanes hold the bottom third. Measured on the delivered frame at the
# winner's crossing the leading marble is **58 x 64 px** against V17's 46
# predicted, and the second is up the channel a clear frame-quarter behind it.
#
# The push is a slow tighten rather than a push-in: the drama here is *early* -
# the winner crosses 0.65 s into a 3.4 s shot - so a lens that starts wide would
# be widest exactly when the 0.283 s gap has to read. It opens at the framing it
# needs and closes 12% over the run-out.
EDIT_V19: tuple[tuple, ...] = EDIT_V18[:-1] + (
    ("finish", 20.20, 23.60, {
        "extent": 16.0,
        "elevation": 43.0,
        "bearing": 25.0,
        "side": -1,
        "target": "node",
        "node": "finish_line",
        "orbit": (-2.0, 2.0),
        "dolly": (0.03, -0.12),
    }),
)

EDITS = {"v18": EDIT_V18, "v19": EDIT_V19}


SMOOTH_PASSES = 14

# How far the sight line has to clear the ground, in layout units, and how far
# the elevation may be raised to get there. One marble diameter of daylight is
# enough to read as clear rather than as grazing; 46 degrees is where a shot
# stops being a camera on the mountain and becomes a plan view, and section 34
# is explicit that there is to be no fixed tower.
SIGHT_MARGIN = 0.6
MAX_ELEVATION = 46.0
LIFT_STEP = 2.0


# --- progress -------------------------------------------------------------


def _route_offsets(runs) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Arc offsets per run per route, for the routes the machine carries.

    A course built with `routes="blue"` has no orange lead, so orange is not on
    offer and is not tabulated - which is what makes the camera solver work
    against either build without a flag of its own.
    """
    offsets: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for route, names in ROUTE_RUNS.items():
        if any(name not in runs for name in names):
            continue
        total = 0.0
        table: dict[str, float] = {}
        for name in names:
            table[name] = total
            total += runs[name].sim_arc[-1]
        offsets[route] = table
        totals[route] = total
    return offsets, totals


def progress_track(replay: dict[str, Any], machine) -> dict[str, Any]:
    """Per-frame progress, run and sample for every marble.

    A windowed nearest-sample search seeded from the previous frame, which is
    what makes this affordable: 8 marbles over 900 frames against 29 candidates
    each rather than against all 800 samples of the course.

    Route comes from the replay's own `route` events, so it is the route the
    physics recorded rather than one re-derived from geometry.
    """
    runs = machine.runs
    offsets, totals = _route_offsets(runs)
    routes: dict[int, str] = {}
    for event in replay["events"]:
        if event["kind"] == "route":
            routes[int(event["id"])] = str(event["route"])

    # The replay flattens an event's payload into the event itself - `{"t":
    # 1.8, "kind": "collision", "a": 3, "b": 6}` - rather than nesting it under
    # a `data` key, which is what `marble3d.replay.Event.to_json` does and what
    # this reader was written against the dataclass instead of the document.
    frames = replay["frames"]
    marbles = [int(m["id"]) for m in replay["marbles"]]
    where: dict[int, tuple[str, int]] = {}
    progress: dict[int, list[float]] = {m: [] for m in marbles}
    places: dict[int, list[tuple[str, int]]] = {m: [] for m in marbles}
    window = 18

    for frame in frames:
        for sample in frame["marbles"]:
            marble_id = int(sample["id"])
            position = sample["p"]
            route = routes.get(marble_id, "blue")
            if route not in offsets:
                route = next(iter(offsets))
            names = tuple(name for name in ROUTE_RUNS[route] if name in runs)
            previous = where.get(marble_id)
            candidates = [previous[0]] if previous else list(names)
            if previous:
                index = names.index(previous[0])
                if index + 1 < len(names):
                    candidates.append(names[index + 1])
            best: tuple[float, str, int] | None = None
            for name in candidates:
                run = runs[name]
                if previous and previous[0] == name:
                    low = max(0, previous[1] - window)
                    high = min(len(run.sim_path), previous[1] + window + 1)
                else:
                    low, high = 0, min(len(run.sim_path), window + 1)
                for at in range(low, high):
                    point = run.sim_path[at]
                    distance = (
                        (position[0] - point[0]) ** 2
                        + (position[1] - point[1]) ** 2
                        + (position[2] - point[2]) ** 2
                    )
                    if best is None or distance < best[0]:
                        best = (distance, name, at)
            if best is None:
                progress[marble_id].append(
                    progress[marble_id][-1] if progress[marble_id] else 0.0
                )
                places[marble_id].append(previous or (names[0], 0))
                continue
            _distance, name, at = best
            where[marble_id] = (name, at)
            value = offsets[route][name] + runs[name].sim_arc[at]
            if progress[marble_id]:
                value = max(value, progress[marble_id][-1])
            progress[marble_id].append(value)
            places[marble_id].append((name, at))

    return {
        "marbles": marbles,
        "routes": routes,
        "progress": progress,
        "places": places,
        "totals": totals,
        "times": [float(frame["t"]) for frame in frames],
    }


def _station_time(track: dict[str, Any], machine, station: str) -> float:
    """When the leader first reaches one station."""
    runs = machine.runs
    offsets, _totals = _route_offsets(runs)
    run_name, fraction = STATIONS[station]
    route = next(
        (name for name, table in offsets.items() if run_name in table),
        next(iter(offsets)),
    )
    if run_name not in offsets[route]:
        # A station on a route this build does not carry: fall back to the end
        # of the shared prefix, so a cut boundary still lands somewhere real.
        return track["times"][-1]
    target = offsets[route][run_name] + fraction * runs[run_name].sim_arc[-1]
    times = track["times"]
    for index, when in enumerate(times):
        best = max(track["progress"][m][index] for m in track["marbles"])
        if best >= target:
            return when
    return times[-1]


# --- the track ------------------------------------------------------------


def _smooth(points: list[tuple[float, float, float]], passes: int) -> list[tuple[float, float, float]]:
    current = list(points)
    for _ in range(passes):
        nxt = []
        for index in range(len(current)):
            a = current[max(index - 1, 0)]
            b = current[index]
            c = current[min(index + 1, len(current) - 1)]
            nxt.append(tuple((a[axis] + b[axis] + c[axis]) / 3.0 for axis in range(3)))
        current = nxt
    return current


def _on_course(machine, offsets, route: str, progress: float):
    """The point on the racing line at `progress` along `route`, in layout units.

    ## Why an aim is projected onto the course at all

    A pack aim was the centroid of the chosen racers' positions, and at a
    hairpin that is not a point on the course. Leg 1's apex turns the course
    back on itself; average a field spread across both legs of the turn and the
    average lands between them - which is *inside the hillside*. The terrain
    check caught it as a sight line the ground crossed by 3.51 layout units at
    46 degrees of elevation, and no bearing fixed it, because the thing being
    aimed at was under the mountain rather than the camera being behind it.
    Measured at that frame: aim y 20.76 against a ground height of 24.27, and
    the port agrees with the scene's own dump to 0.0025 at the four nearest
    grid points, so the ground really was above the aim.

    It also explains the two frames that read worst in the first
    full-resolution pass - `long` and `hairpin`, the two turns - as the same
    fault rather than two accidents of framing.

    So the aim is the course's own point at the pack's mean progress. It is on
    the racing line by construction, at every field spread and every turn, and
    the terrain check goes back to being a statement about where the camera is
    standing. The marble radius is added because a racer's centre rides that
    far above the channel's centreline.
    """
    names = ROUTE_RUNS[route]
    table = offsets[route]
    chosen = names[0]
    for name in names:
        if progress >= table[name] - 1e-9:
            chosen = name
    run = machine.runs[chosen]
    index = run.index_at_length(progress - table[chosen])
    point = run.sim_path[index]
    return (
        point[0] * SIM_TO_LAYOUT,
        point[1] * SIM_TO_LAYOUT + layout.MARBLE_RADIUS,
        point[2] * SIM_TO_LAYOUT,
    )


def _pack_aim(machine, offsets, track, chosen, index) -> tuple[float, float, float]:
    """Where to look when the pack is on more than one route.

    The aim used to be `_on_course(leader's route, mean progress of everyone)`,
    and on a two-route course that is wrong twice over: the mean is contaminated
    by racers whose progress is measured along a *different* run, and the point
    it produces is on the leader's lobe with the other lobe's racers nowhere
    near the frame. Measured on the selected seed's `branch` cut, the pack is
    two orange and one blue and the shot held **two racers of eight**; and when
    the lead changes across the fork the aim steps from one lobe to the other,
    which `check_track` reported as an aim moving 1.067 layout units in a frame
    against a fastest racer's 0.530.

    So each route present in the pack is projected onto its **own** run at its
    **own** members' mean progress, and the aim is those points averaged by
    member count. Between two lobes that is a point between them, which is what
    a camera watching a split has to look at; on one route it is exactly the
    old expression, which is what keeps every blue-only track reproducing.
    """
    by_route: dict[str, list[int]] = {}
    for marble in chosen:
        by_route.setdefault(track["routes"][marble] or "blue", []).append(marble)
    points: list[tuple[float, float, float]] = []
    weights: list[float] = []
    for route, members in by_route.items():
        if route not in offsets:
            route = next(iter(offsets))
        mean = sum(track["progress"][marble][index] for marble in members) / len(members)
        points.append(_on_course(machine, offsets, route, mean))
        weights.append(float(len(members)))
    total = sum(weights)
    return tuple(
        sum(point[axis] * weight for point, weight in zip(points, weights)) / total
        for axis in range(3)
    )


def _place(aim, spun, elevation_deg: float, reach: float) -> tuple[float, float, float]:
    """A camera position from an aim, a horizontal bearing and an elevation."""
    elevation = math.radians(elevation_deg)
    direction = (
        spun[0] * math.cos(elevation),
        math.sin(elevation),
        spun[2] * math.cos(elevation),
    )
    return tuple(aim[axis] + direction[axis] * reach for axis in range(3))


def _heading_at(machine, place: tuple[str, int]) -> tuple[float, float, float]:
    run = machine.runs[place[0]]
    at = min(max(place[1], 0), len(run.tangents) - 1)
    return run.tangents[at]


def build_track(
    replay: dict[str, Any],
    machine,
    sections: Sequence[Cut] = SECTIONS,
    fps: int = 60,
    edit: Sequence[tuple] | None = None,
) -> dict[str, Any]:
    """A position, an aim and a field of view per frame, in layout units.

    `edit` replaces the station clock with an explicit list of
    `(lens, replay from, replay to[, overrides])` windows. The windows need not
    be contiguous, so the track then carries an **edit map** from output time to
    replay time - slope one throughout, so replay time is omitted rather than
    compressed and no marble's speed changes.
    """
    track = progress_track(replay, machine)
    times = track["times"]
    frames = replay["frames"]

    # When the last marble crossed the line. The clip ends a beat after that
    # rather than at the end of the replay: the physics keeps running while the
    # field rolls out onto the finish deck and settles, which is eleven seconds
    # of a thirty-second record on the reference seed and none of it is a race.
    # Section 40 allows a camera to omit a visually unimportant tail; it does
    # not allow the *timing* to be altered, and nothing here is sped up.
    crossings = [
        float(event["t"]) for event in replay["events"] if event["kind"] == "finish_line"
    ]
    last_crossing = max(crossings) if crossings else times[-1]

    # Each cut runs until its station is reached, with a floor and an optional
    # ceiling on its own length - and every bound clamped to the replay.
    #
    # The clamp is not defensive tidying. Without it a replay that ends before
    # the field reaches the later stations gives those cuts bounds beyond its
    # last frame, and the finish cut - whose end is pulled back to the replay -
    # comes out with a *negative* duration: on a twelve-second race it was
    # -1.500 s, a cut that starts a second and a half after it ends. Every
    # check downstream then reads a track whose cuts do not tile its own
    # timeline. Production replays are long enough that this never showed in a
    # frame, which is exactly why it needed a test rather than a render.
    horizon = times[-1]
    bounds: list[tuple[float, float]] = []
    start = 0.0
    for cut in sections:
        end = _station_time(track, machine, cut.until) + cut.hold
        end = max(end, start + cut.min_seconds)
        if cut.max_seconds > 0.0:
            end = min(end, start + cut.max_seconds)
        start = min(start, horizon)
        end = min(max(end, start), horizon)
        bounds.append((start, end))
        start = end
    bounds[-1] = (
        bounds[-1][0],
        min(horizon, max(bounds[-1][1], last_crossing + sections[-1].hold)),
    )

    if edit:
        # The editor's own windows, clamped to the replay and in its order.
        lenses = {cut.name: cut for cut in sections}
        kept = []
        for entry in edit:
            name, low, high = entry[0], float(entry[1]), float(entry[2])
            overrides = dict(entry[3]) if len(entry) > 3 else {}
            lens = lenses.get(name)
            if lens is None:
                raise KeyError(f"the edit names a lens the cut list has not: {name!r}")
            low = max(0.0, min(low, horizon))
            high = max(low, min(high, horizon))
            if high - low <= 1e-6:
                continue
            kept.append((dataclasses.replace(lens, **overrides), (low, high)))
        if not kept:
            raise ValueError("the edit kept nothing")
    else:
        # A cut the replay left no room for is dropped rather than emitted
        # empty, so `check_track` never has to reason about a zero-length shot.
        kept = [
            (cut, span)
            for cut, span in zip(sections, bounds)
            if span[1] - span[0] > 1e-6
        ]
        if not kept:
            kept = [(sections[0], (0.0, horizon))]
    sections = tuple(cut for cut, _span in kept)
    bounds = [span for _cut, span in kept]

    offsets, _totals = _route_offsets(machine.runs)
    # **The start node is the authored one and the start module is not on it.**
    # `sloped.trapdoor.ShuffleFloor` derives its own lift and stands 3.93 layout
    # units above `layout.NODES["start"]`, so a camera aimed at the node aims
    # at the empty air under the machine - which is what the V1.15 start cut
    # did. Taken from the module rather than from a constant, so a start that
    # derives a different lift moves the camera with it.
    nodes = dict(layout.NODES)
    start = machine.modules.get("start")
    if start is not None and hasattr(start, "origin"):
        nodes["start"] = tuple(float(value) for value in start.origin)
    # **`layout.NODES["split"]` is not the fork.** It sits at (6.0, 10.5, 18.0),
    # which is where *blue's lead* begins - 10.9 layout units downstream of the
    # divider, with orange's lead already gone. A camera aimed at it frames the
    # aftermath of a choice and never the choice, which is what the V1.15
    # review found in all three `split` frames. The fork is leg3's own fork
    # sample, taken from the built run so it moves if the junction does.
    runs = machine.runs if hasattr(machine, "runs") else {}
    leg3 = runs.get("leg3")
    if leg3 is not None:
        at = min(joins.FORK_SAMPLE, len(leg3.sim_path) - 1)
        mouths = [leg3.sim_path[at]]
        # **The midpoint of the two mouths, not the divider.** Aimed at the
        # divider alone the shot holds the divider and one lobe; aimed between
        # the two lead entries it holds the divider, both mouths and the leg
        # arriving at them, which is the whole of the decision.
        for name in ("blue_lead", "orange_lead"):
            branch = runs.get(name)
            if branch is not None:
                mouths.append(branch.sim_path[0])
        nodes["fork"] = (
            sum(point[0] for point in mouths) / len(mouths) * SIM_TO_LAYOUT,
            sum(point[1] for point in mouths) / len(mouths) * SIM_TO_LAYOUT
            + layout.MARBLE_RADIUS,
            sum(point[2] for point in mouths) / len(mouths) * SIM_TO_LAYOUT,
        )
    # **The line itself, for a camera that should not be following anybody.**
    # `target = "pair"` is the midpoint of the leading two *by progress*, and a
    # marble that has crossed and is rolling out across the deck has left the
    # route the progress is measured along - so its projection slides back down
    # `final` and it drops out of the leading pair it just won. On the selected
    # seed the finish cut's own subject came out marbles 2 and 7, which are
    # second and third: the winner had already crossed at the midpoint and was
    # no longer, by that measure, in front.
    #
    # A finish does not need to be followed. The racers come to the line, so the
    # line is the aim, taken from the built run's last sample and raised a
    # radius to where a marble's centre crosses it.
    final_run = runs.get("final")
    if final_run is not None:
        end = final_run.path[-1]
        nodes["finish_line"] = (end[0], end[1] + layout.MARBLE_RADIUS, end[2])
    metrics_aim = (1.0, 18.0, 6.0)          # layout B's own hero aim
    cfg = terrain.terrain_config(machine.runs)

    cuts_out: list[dict[str, Any]] = []
    for cut, (from_time, to_time) in zip(sections, bounds):
        indices = [i for i, when in enumerate(times) if from_time <= when <= to_time]
        if not indices:
            indices = [min(range(len(times)), key=lambda i: abs(times[i] - from_time))]

        # Who the shot is of, decided once, at the cut's own midpoint.
        #
        # This was decided per frame, and per frame is wrong for a reason that
        # took measuring the aim's speed to see. A pack is the racers within
        # `band` of the leader; re-deciding membership every frame means that
        # when a racer crosses the band edge the centroid of the set moves by a
        # fraction of the gap to that racer, and a centroid can therefore move
        # faster than any racer in it. At the fork, where the field is at its
        # most strung out, the aim moved 1.8 times as fast as the quickest
        # marble on the course - the camera was chasing an arithmetic artefact,
        # not the field. Widening the band barely touched it, which is what
        # ruled membership *at the edge* out as the cause.
        #
        # A fixed set can only move as its members move, so the aim is slower
        # than the fastest racer in the shot by construction, and there is
        # nothing left to tune.
        middle_index = min(indices, key=lambda i: abs(times[i] - 0.5 * (from_time + to_time)))
        ranked = sorted(track["marbles"], key=lambda m: -track["progress"][m][middle_index])
        if cut.target == "leader":
            chosen = ranked[:1]
        elif cut.target == "pair":
            chosen = ranked[:2]
        else:
            front = track["progress"][ranked[0]][middle_index]
            chosen = [
                m for m in ranked if track["progress"][m][middle_index] >= front - cut.band
            ] or ranked[:1]

        aims: list[tuple[float, float, float]] = []
        headings: list[tuple[float, float, float]] = []
        for index in indices:
            frame = frames[index]
            if cut.target == "node":
                point = metrics_aim if cut.node == "hero" else nodes[cut.node]
                aims.append(tuple(float(v) for v in point))
                lead = ranked[0]
                headings.append(_heading_at(machine, track["places"][lead][index]))
                continue
            # The pack's mean progress, put back on the course - **per route,
            # and then averaged between them**. See `_on_course` for why the
            # centroid of the positions themselves is not a point on the
            # course at a turn, and `_pack_aim` for why one route is not
            # enough once the field is on two.
            aims.append(_pack_aim(machine, offsets, track, chosen, index))
            # The heading is the *course's* heading at the pack, taken from the
            # leader's own place, which is what the bearing is measured from.
            headings.append(_heading_at(machine, track["places"][chosen[0]][index]))

        # The quickest racer still in play over the cut, in layout units a
        # second: what the aim's own speed has to be judged against.
        fastest = 0.0
        for index in indices:
            for sample in frames[index]["marbles"]:
                if sample.get("s") != "running":
                    continue
                fastest = max(
                    fastest,
                    math.sqrt(sum(float(v) ** 2 for v in sample["v"])) * SIM_TO_LAYOUT,
                )

        aims = _smooth(aims, SMOOTH_PASSES)
        headings = _smooth(headings, SMOOTH_PASSES + 3)

        distance = 0.5 * cut.extent / max(math.tan(math.radians(cut.fov) * 0.5), 1e-6)
        entries: list[list[float]] = []
        lifts: list[float] = []
        clearances: list[float] = []
        span = max(len(indices) - 1, 1)
        for step, index in enumerate(indices):
            u = step / span
            orbit = cut.orbit[0] + (cut.orbit[1] - cut.orbit[0]) * u
            dolly = cut.dolly[0] + (cut.dolly[1] - cut.dolly[0]) * u
            aim = aims[step]
            forward = headings[step]
            flat = (forward[0], 0.0, forward[2])
            length = math.hypot(flat[0], flat[2])
            if length < 1e-6:
                flat = (0.0, 0.0, 1.0)
                length = 1.0
            flat = (flat[0] / length, 0.0, flat[2] / length)

            # The bearing swings toward whichever side stands over lower
            # ground, so a side-on shot is never inside the hill - unless the
            # cut names its own side, in which case it is that perpendicular
            # for the whole shot and the ground is not asked. See `Cut.side`.
            if cut.side:
                base = (flat[2], 0.0, -flat[0])
                base_length = math.hypot(base[0], base[2]) or 1.0
                sign = 1.0 if cut.side > 0 else -1.0
                side = (base[0] / base_length * sign, 0.0, base[2] / base_length * sign)
            else:
                side = terrain.lower_side(aim, flat, cfg)
            angle = math.radians(cut.bearing + orbit)
            spun = (
                flat[0] * math.cos(angle) + side[0] * math.sin(angle),
                0.0,
                flat[2] * math.cos(angle) + side[2] * math.sin(angle),
            )
            spun_length = math.hypot(spun[0], spun[2])
            if spun_length > 1e-9:
                spun = (spun[0] / spun_length, 0.0, spun[2] / spun_length)
            reach = distance * (1.0 + dolly)

            elevation = cut.elevation
            position = _place(aim, spun, elevation, reach)
            gap = terrain.clearance(position, aim, cfg)
            while gap < SIGHT_MARGIN and elevation < MAX_ELEVATION:
                elevation = min(MAX_ELEVATION, elevation + LIFT_STEP)
                position = _place(aim, spun, elevation, reach)
                gap = terrain.clearance(position, aim, cfg)
            lifts.append(elevation - cut.elevation)
            clearances.append(gap)

            entries.append(
                [
                    round(times[index], 6),
                    round(position[0], 4),
                    round(position[1], 4),
                    round(position[2], 4),
                    round(aim[0], 4),
                    round(aim[1], 4),
                    round(aim[2], 4),
                    round(cut.fov, 3),
                ]
            )
        cuts_out.append(
            {
                **cut.to_json(),
                "from": round(from_time, 6),
                "to": round(to_time, 6),
                "distance": round(distance, 4),
                "fastest_racer": round(fastest, 4),
                "subject": sorted(chosen),
                "lift_deg": round(max(lifts), 3) if lifts else 0.0,
                "min_clearance": round(min(clearances), 3) if clearances else 0.0,
                "frames": entries,
            }
        )

    # The edit map: output time to replay time, one entry per kept window and
    # **slope one** in every one of them. Without an edit it is the identity,
    # so a track built the old way maps output onto replay unchanged.
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for cut, (low, high) in zip(sections, bounds):
        span = high - low
        segments.append(
            {
                "cut": cut.name,
                "out": [round(cursor, 6), round(cursor + span, 6)],
                "replay": [round(low, 6), round(high, 6)],
            }
        )
        cursor += span
    edited = bool(edit)
    return {
        "units": "layout",
        "fps": fps,
        "seed": replay["seed"],
        "edited": edited,
        # What the renderer walks. Equal to the replay duration when there is
        # no edit, and the sum of the kept windows when there is.
        "duration": round(cursor if edited else bounds[-1][1], 6),
        "replay_duration": times[-1],
        "omitted": round(max(0.0, (bounds[-1][1] - bounds[0][0]) - cursor), 6),
        "last_crossing": round(last_crossing, 6),
        "edit": segments,
        "cuts": cuts_out,
    }


def write_track(track: dict[str, Any], path: str) -> str:
    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(track, handle, separators=(",", ":"))
        handle.write("\n")
    return path


# What a racer has to be for a frame to be a frame of a race. Both measured
# against the output frame rather than chosen: 1080x1920 is the delivery size,
# and a sphere under about twenty pixels across in it is a coloured dot that a
# viewer reads as scenery. Two racers is the least that can show a position.
# How much faster than the quickest racer in the shot the aim may travel before
# it is chasing rather than following. Not 1.0: the aim is a smoothed centroid
# and its own filter overshoots slightly at a cut's ends, and the racer speed is
# read from the replay's 60 Hz samples while the physics ran at 240.
AIM_SPEED_HEADROOM = 1.15

MIN_RACERS_IN_FRAME = 2
MIN_RACER_PIXELS = 24.0
MAX_AIM_DRIFT = 6.0             # layout units: ten diameters off the field


def frame_report(
    track: dict[str, Any],
    replay: dict[str, Any],
    width: int = 1080,
    height: int = 1920,
) -> list[dict[str, Any]]:
    """Per cut, at its midpoint: how much of the field is actually in shot.

    The gap this closes is the one that cost a full-resolution still pass. The
    checks below confirm the camera is above its aim, that the aim follows
    something, and that the mountain is not in the way - and all of them passed
    on a cut whose nearest racer was ten units off the aim point, because none
    of them asks the question a viewer asks first: *can I see the marbles.*

    So this projects every racer into the cut's own frustum and reports the
    count that lands inside it and the apparent diameter of the nearest, in
    pixels of the delivered frame. Godot's Camera3D keeps height by default, so
    the vertical half-angle is the fov and the horizontal one follows from the
    aspect - which for a 1080x1920 portrait frame is the *narrow* axis, and
    getting that backwards would report a comfortable margin on the axis that
    is actually the tight one.

    It cannot see occlusion. A racer inside its own channel with the guard rail
    between it and a low camera counts as in frame here and is invisible in the
    render, which is why `branch` needed a still and not only this.
    """
    frames = replay.get("frames", [])
    if not frames:
        return []
    scale = float(replay.get("units", {}).get("render_scale", SIM_TO_LAYOUT))
    radius = float(replay.get("units", {}).get("layout_marble_radius", layout.MARBLE_RADIUS))
    times = [float(frame["t"]) for frame in frames]

    report: list[dict[str, Any]] = []
    for cut in track["cuts"]:
        entries = cut.get("frames") or []
        if not entries:
            continue
        middle = 0.5 * (cut["from"] + cut["to"])
        entry = min(entries, key=lambda row: abs(row[0] - middle))
        position = tuple(entry[1:4])
        aim = tuple(entry[4:7])
        fov = float(entry[7])

        index = min(range(len(times)), key=lambda k: abs(times[k] - middle))
        racers = [
            tuple(float(marble["p"][axis]) * scale for axis in range(3))
            for marble in frames[index]["marbles"]
        ]
        if not racers:
            continue

        forward = [aim[axis] - position[axis] for axis in range(3)]
        reach = math.sqrt(sum(value * value for value in forward)) or 1.0
        forward = [value / reach for value in forward]
        right = [forward[2], 0.0, -forward[0]]
        length = math.hypot(right[0], right[2]) or 1.0
        right = [right[0] / length, 0.0, right[2] / length]
        up = [
            right[1] * forward[2] - right[2] * forward[1],
            right[2] * forward[0] - right[0] * forward[2],
            right[0] * forward[1] - right[1] * forward[0],
        ]
        half_up = math.tan(math.radians(fov) * 0.5)
        half_across = half_up * (width / height)

        inside: list[float] = []
        for racer in racers:
            offset = [racer[axis] - position[axis] for axis in range(3)]
            depth = sum(offset[axis] * forward[axis] for axis in range(3))
            if depth <= 0.05:
                continue
            across = sum(offset[axis] * right[axis] for axis in range(3)) / depth
            upward = sum(offset[axis] * up[axis] for axis in range(3)) / depth
            if abs(across) <= half_across and abs(upward) <= half_up:
                inside.append(math.dist(position, racer))
        nearest_px = 0.0
        if inside:
            nearest_px = (2.0 * radius / min(inside)) / (2.0 * half_up) * height
        report.append(
            {
                "cut": cut["name"],
                "at": round(middle, 3),
                "target": cut["target"],
                "in_frame": len(inside),
                "of": len(racers),
                "nearest_px": round(nearest_px, 1),
                "aim_to_nearest": round(min(math.dist(aim, racer) for racer in racers), 3),
            }
        )
    return report


def check_track(track: dict[str, Any], replay: dict[str, Any] | None = None) -> list[str]:
    """What a camera track can be wrong about without anything being rendered.

    Not a substitute for looking at the frames - section 37 asks for terrain
    clearance and no arithmetic here knows where the mountain is - but these
    four are the ones that are cheap and that a reviewer would otherwise have
    to spot by eye:

    * a cut shorter than a third of a second, which reads as a glitch;
    * a camera below the aim point, which means the elevation went negative
      somewhere and the shot is looking up through the track;
    * an aim point that moves faster than the fastest racer in its own cut,
      which is what "snapping rather than following" actually means - a
      diameter per frame was the first threshold here and it was the wrong
      quantity, because a field descending at 24 layout units a second covers
      most of a diameter per frame legitimately;
    * a gap or an overlap between consecutive cuts;
    * a sight line the mountain still crosses after the lift ran out of
      elevation, which is section 37's check and the one that needed the
      terrain ported to make.
    """
    problems: list[str] = []
    fps = max(float(track.get("fps", 60.0)), 1.0)
    previous_end: float | None = None
    for cut in track["cuts"]:
        span = cut["to"] - cut["from"]
        if span < 0.34:
            problems.append(f"{cut['name']}: {span:.3f} s is too short to read as a shot")
        # **A gap between two cuts is an edit, not a fault.** `SECTIONS` tiles
        # the replay, so on an unedited track a cut that does not start where
        # the last one ended is a bug; on an edited one it is the whole point -
        # V18 omits 3.55 s of mixing and 1.05 s of spinner corridor with two
        # intentional jumps. Output time still runs at slope one through every
        # window, which is what the edit map carries and what the rate test pins.
        if (
            not track.get("edited")
            and previous_end is not None
            and abs(cut["from"] - previous_end) > 1e-6
        ):
            problems.append(
                f"{cut['name']}: starts at {cut['from']:.3f} against the previous "
                f"cut's end at {previous_end:.3f}"
            )
        previous_end = cut["to"]
        if not cut["frames"]:
            problems.append(f"{cut['name']}: no frames")
            continue
        if cut.get("min_clearance", 1.0) < 0.0:
            problems.append(
                f"{cut['name']}: the ground crosses the sight line by "
                f"{-cut['min_clearance']:.2f} layout units even at "
                f"{cut['elevation'] + cut.get('lift_deg', 0.0):.0f} degrees of elevation"
            )
        for entry in cut["frames"]:
            if entry[2] <= entry[5]:
                problems.append(
                    f"{cut['name']} at {entry[0]:.2f}s: camera at y={entry[2]:.2f} is "
                    f"not above its aim at y={entry[5]:.2f}"
                )
                break
        worst = 0.0
        for a, b in zip(cut["frames"], cut["frames"][1:]):
            worst = max(worst, math.dist(a[4:7], b[4:7]))
        limit = AIM_SPEED_HEADROOM * max(
            cut.get("fastest_racer", 0.0) / fps, layout.MARBLE_RADIUS
        )
        if worst > limit:
            problems.append(
                f"{cut['name']}: the aim moves {worst:.3f} layout units in a frame "
                f"against a fastest racer's {cut.get('fastest_racer', 0.0) / fps:.3f}"
            )

    if replay is not None:
        for row in frame_report(track, replay):
            # The establishing shot is the one cut whose subject is the course
            # rather than the field, so its racers are meant to be specks; it is
            # capped at under a second for that reason.
            if row["cut"] == "establish":
                continue
            if row["in_frame"] < MIN_RACERS_IN_FRAME:
                problems.append(
                    f"{row['cut']}: {row['in_frame']} of {row['of']} racers are in "
                    f"frame at {row['at']:.2f}s"
                )
            if row["nearest_px"] < MIN_RACER_PIXELS:
                problems.append(
                    f"{row['cut']}: the nearest racer is {row['nearest_px']:.0f} px "
                    f"across at {row['at']:.2f}s, which reads as scenery"
                )
            if row["target"] != "node" and row["aim_to_nearest"] > MAX_AIM_DRIFT:
                problems.append(
                    f"{row['cut']}: the aim is {row['aim_to_nearest']:.1f} layout "
                    f"units from the nearest racer, so it is not following the field"
                )
    return problems

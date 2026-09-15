"""Race #2: a compact, event-dense marble race and the camera language for it.

Race #1 (`sloped.*`) is a 237-layout-unit zig-zag raceway with five mechanisms
on it, and the analytics from Race Test #2 say what is wrong with that shape as
*content*: the opening works, viewers stay to watch, and then the middle has
nothing to say for seconds at a time. Five events over 237 units of track is one
question every 47 units, and at 9 to 15 layout units a second that is a question
every three to five seconds with rolling in between.

This package is the second course, and it is organised around one number:
**the longest span in which nothing competitively meaningful changes.** Not
duration, not prettiness, not mechanism count. Everything here - the folded
plan, the short runs, the wide dished band, the module spacing, the camera
modes - exists to push that number down.

Nothing in `sloped` is imported for its *decisions*; what is imported is its
*primitives*, because they carry measured corrections that would otherwise be
rediscovered: `sloped.track.TrackRun` is the banked channel with its guard
windows and bank slew, `sloped.stations.Spinners` is the blade wheel that
sweeps the clear width without passing through the floor, `sloped.scale` is the
one place layout units and simulation units meet, and
`sloped.trapdoor.FloorPanel` is the hinged louvre whose pose is a pure function
of the tick. Race #1 itself is untouched, and `tests/test_race2_isolation.py`
is what says so.
"""

__all__ = []

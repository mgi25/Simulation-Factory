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
from dataclasses import dataclass, field
from typing import Any, Sequence

from sloped import layout, terrain
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
    Cut("start", "launched", fov=34.0, extent=9.5, elevation=16.0, bearing=28.0,
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
    Cut("split", "promontory", fov=34.0, extent=28.0, elevation=26.0, bearing=8.0,
        target="pack", band=56.0, orbit=(5.0, -5.0), min_seconds=1.2),
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
    Cut("finish", "line", fov=36.0, extent=15.0, elevation=20.0, bearing=155.0,
        target="pair", orbit=(-4.0, 3.0), dolly=(0.14, -0.10), hold=1.7,
        min_seconds=1.6),
)

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
) -> dict[str, Any]:
    """A position, an aim and a field of view per frame, in layout units."""
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

    # A cut the replay left no room for is dropped rather than emitted empty,
    # so `check_track` never has to reason about a zero-length shot.
    kept = [
        (cut, span) for cut, span in zip(sections, bounds) if span[1] - span[0] > 1e-6
    ]
    if not kept:
        kept = [(sections[0], (0.0, horizon))]
    sections = tuple(cut for cut, _span in kept)
    bounds = [span for _cut, span in kept]

    offsets, _totals = _route_offsets(machine.runs)
    nodes = dict(layout.NODES)
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
            # ground, so a side-on shot is never inside the hill.
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

    return {
        "units": "layout",
        "fps": fps,
        "seed": replay["seed"],
        "duration": round(bounds[-1][1], 6),
        "replay_duration": times[-1],
        "last_crossing": round(last_crossing, 6),
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
        if previous_end is not None and abs(cut["from"] - previous_end) > 1e-6:
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

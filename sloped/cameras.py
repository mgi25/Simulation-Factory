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

That also means a camera can be checked before anything is rendered.
`tools/sloped_cameras.py --check` reports, per cut, how far the subject is from
frame centre, how much of the frame the pack fills, and whether the aim point
ever leaves the cut's own section of the course.

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

from sloped import layout
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
]


# Where the leader has to get to for each cut to end, as a run and a fraction
# along it. Read as a list of stations rather than of times.
STATIONS = {
    "grid": ("launch", 0.0),
    "descent": ("launch", 0.55),
    "mixer": ("leg1", 0.10),
    "leg1_hairpin": ("leg1", 0.80),
    "long": ("leg2", 0.30),
    "obstacle": ("leg2", 0.90),
    "sweep": ("leg3", 0.45),
    "fork": ("leg3", 0.70),
    "branch": ("blue", 0.45),
    "merge": ("final", 0.02),
    "sprint": ("final", 0.55),
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


# The sequence. Eight cuts for section 35's eight sections, plus a
# three-quarter-second establishing frame that section 39 allows and caps.
#
# The bearings are the one thing here that is a *style* decision rather than an
# arithmetic one, and they follow section 38: a close three-quarter view for the
# grid, a low side follow down the first descent, an outside tracking shot
# through the fast bends, a high compression view over the hairpin, tight on the
# spinners, wide and elevated over the split so both routes are in frame,
# facing the convergence at the merge, low behind the sprint, and a warm
# push-in at the line. Bearing is measured from the track's own forward
# direction at the aim point, so 0 looks back up the course at the field coming
# on, 90 is side-on and 180 follows from behind.
SECTIONS: tuple[Cut, ...] = (
    Cut("establish", "grid", fov=30.0, extent=150.0, elevation=17.0, bearing=200.0,
        target="node", node="hero", orbit=(-2.0, 2.0), min_seconds=0.75, hold=0.0),
    Cut("start", "descent", fov=34.0, extent=9.0, elevation=16.0, bearing=28.0,
        target="node", node="start", orbit=(-6.0, 4.0), dolly=(0.10, -0.06), hold=0.25),
    Cut("descent", "mixer", fov=36.0, extent=8.0, elevation=9.0, bearing=104.0,
        target="pack", band=26.0, orbit=(4.0, -4.0)),
    Cut("long", "leg1_hairpin", fov=36.0, extent=13.0, elevation=13.0, bearing=150.0,
        target="pack", band=40.0, dolly=(0.04, -0.04)),
    Cut("hairpin", "long", fov=34.0, extent=12.0, elevation=27.0, bearing=52.0,
        target="pack", band=40.0, orbit=(-7.0, 5.0)),
    Cut("straight", "obstacle", fov=36.0, extent=16.0, elevation=11.0, bearing=118.0,
        target="pack", band=48.0, dolly=(0.06, -0.05)),
    Cut("obstacle", "sweep", fov=32.0, extent=7.5, elevation=15.0, bearing=44.0,
        target="pack", band=22.0, orbit=(-8.0, 5.0), hold=0.2),
    Cut("split", "branch", fov=34.0, extent=19.0, elevation=23.0, bearing=22.0,
        target="pack", band=70.0, orbit=(6.0, -6.0), hold=0.3),
    Cut("merge", "sprint", fov=34.0, extent=12.0, elevation=15.0, bearing=6.0,
        target="pack", band=44.0, dolly=(0.05, -0.05)),
    Cut("finish", "line", fov=36.0, extent=13.0, elevation=12.0, bearing=168.0,
        target="pair", orbit=(-4.0, 3.0), dolly=(0.14, -0.10), hold=1.6),
)

SMOOTH_PASSES = 5


# --- progress -------------------------------------------------------------


def _route_offsets(runs) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    offsets: dict[str, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for route, names in ROUTE_RUNS.items():
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
            routes[int(event["data"]["id"])] = str(event["data"]["route"])

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
            names = ROUTE_RUNS[route]
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
    route = "blue" if run_name in ROUTE_RUNS["blue"] else "orange"
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

    bounds: list[tuple[float, float]] = []
    start = 0.0
    for cut in sections:
        end = _station_time(track, machine, cut.until) + cut.hold
        end = max(end, start + cut.min_seconds)
        bounds.append((start, end))
        start = end
    # The last cut runs to the end of the replay whatever its station said, so
    # nothing is trimmed off the finish.
    bounds[-1] = (bounds[-1][0], max(bounds[-1][1], times[-1]))

    nodes = dict(layout.NODES)
    metrics_aim = (1.0, 18.0, 6.0)          # layout B's own hero aim

    cuts_out: list[dict[str, Any]] = []
    for cut, (from_time, to_time) in zip(sections, bounds):
        indices = [i for i, when in enumerate(times) if from_time <= when <= to_time]
        if not indices:
            indices = [min(range(len(times)), key=lambda i: abs(times[i] - from_time))]

        aims: list[tuple[float, float, float]] = []
        headings: list[tuple[float, float, float]] = []
        for index in indices:
            frame = frames[index]
            samples = {int(s["id"]): s["p"] for s in frame["marbles"]}
            order = sorted(
                track["marbles"], key=lambda m: -track["progress"][m][index]
            )
            if cut.target == "node":
                point = metrics_aim if cut.node == "hero" else nodes[cut.node]
                aims.append(tuple(float(v) for v in point))
                lead = order[0]
                headings.append(_heading_at(machine, track["places"][lead][index]))
                continue
            if cut.target == "leader":
                chosen = order[:1]
            elif cut.target == "pair":
                chosen = order[:2]
            else:
                front = track["progress"][order[0]][index]
                chosen = [
                    m for m in order if track["progress"][m][index] >= front - cut.band
                ] or order[:1]
            centre = [0.0, 0.0, 0.0]
            for marble in chosen:
                point = samples[marble]
                for axis in range(3):
                    centre[axis] += point[axis] * SIM_TO_LAYOUT
            aims.append(tuple(value / len(chosen) for value in centre))
            headings.append(_heading_at(machine, track["places"][chosen[0]][index]))

        aims = _smooth(aims, SMOOTH_PASSES)
        headings = _smooth(headings, SMOOTH_PASSES + 3)

        distance = 0.5 * cut.extent / max(math.tan(math.radians(cut.fov) * 0.5), 1e-6)
        entries: list[list[float]] = []
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
            angle = math.radians(cut.bearing + orbit)
            spun = (
                flat[0] * math.cos(angle) + flat[2] * math.sin(angle),
                0.0,
                -flat[0] * math.sin(angle) + flat[2] * math.cos(angle),
            )
            elevation = math.radians(cut.elevation)
            direction = (
                spun[0] * math.cos(elevation),
                math.sin(elevation),
                spun[2] * math.cos(elevation),
            )
            reach = distance * (1.0 + dolly)
            position = tuple(aim[axis] + direction[axis] * reach for axis in range(3))
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
                "frames": entries,
            }
        )

    return {
        "units": "layout",
        "fps": fps,
        "seed": replay["seed"],
        "duration": times[-1],
        "cuts": cuts_out,
    }


def write_track(track: dict[str, Any], path: str) -> str:
    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(track, handle, separators=(",", ":"))
        handle.write("\n")
    return path


def check_track(track: dict[str, Any]) -> list[str]:
    """What a camera track can be wrong about without anything being rendered.

    Not a substitute for looking at the frames - section 37 asks for terrain
    clearance and no arithmetic here knows where the mountain is - but these
    four are the ones that are cheap and that a reviewer would otherwise have
    to spot by eye:

    * a cut shorter than a third of a second, which reads as a glitch;
    * a camera below the aim point, which means the elevation went negative
      somewhere and the shot is looking up through the track;
    * an aim point that moves more than a diameter between two frames, which is
      a target rule snapping rather than following;
    * a gap or an overlap between consecutive cuts.
    """
    problems: list[str] = []
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
        if worst > layout.MARBLE_RADIUS * 2.0:
            problems.append(
                f"{cut['name']}: the aim jumps {worst:.3f} layout units in one frame"
            )
    return problems

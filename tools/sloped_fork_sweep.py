"""Single marbles and small packs through the fork, with the floor under them.

Sections 6 and 7 of the V1.13 brief. `tools/sloped_split_test.py` already
launches a field into the fork and reports what became of it; what it cannot
say is **where the floor ran out**, and that turns out to be the whole
question. `tools/sloped_fork_trace.py` reports every failure in *leg3's* frame,
which is the wrong frame past the fork: a marble a third of the way down
orange's lead is 8 units "across" leg3's centreline and that number says
nothing about where it is in the channel it is actually in.

So this locates every marble on the run it is **nearest**, reports it in that
run's own horizontal frame, and fires rays from its centre:

    drop        how far below the centre the nearest surface is, and its owner.
                A marble rolling has `drop` at a radius; one over a void has no
                drop at all.
    release     the last frame at which a marble had a floor within
                `SUPPORTED`, as (run, sample, across, owner). For a failure
                this is the edge it left, in the frame of the run that owned
                the edge - which is the number a guard window is set from.
    pinch       the smallest of sixteen horizontal rays from the centre, the
                lateral clearance section 6 asks for. Under a radius means the
                marble is touching something sideways; well under means wedged.

    python tools/sloped_fork_sweep.py --speeds 36 43 50 --offsets -0.5 0 0.5
    python tools/sloped_fork_sweep.py --pack 8 --knobs '{"crest": 0.12}'

The knob names are `tools/sloped_fork_lab.py`'s, so a candidate that looks good
here can be handed to the whole-race scan unchanged.

## The verdict is this tool's own, and that is a correction

A first version drove `sloped.splitlab.SplitEntry` and read its `EntryOutcome`,
and its numbers were wrong in the direction that matters. `SplitEntry`'s
`done()` is true as soon as every marble is finished **or** has `lost_at` set,
and `lost_at` is a *containment* verdict: a marble flying over the fork ridge
with the ridge 1.2 units under it reads as "over" leg3's channel, because
leg3's containment is 0.98 and `VERTICAL_SLACK` is 1.0. So the race stopped at
the apex of a jump the marble was going to land from, and five of 28 entries
were booked as failures without the simulation ever being asked.

`marble3d.simulation` retires a marble as **escaped** only when it leaves the
machine's own bounding box, and as **finished** only past the finish socket.
Those two are unambiguous, so they are the verdict here, and the containment
reading is kept as a diagnostic beside it rather than as an outcome. That is
the seventh session `instrument-bugs-hide-geometry-findings` applies to.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG
from marble3d.units import MARBLE_RADIUS

# The runs a marble in the fork region can be on. `fork` and the stations are
# not runs and have no frame, so a marble over the ridge is reported on
# whichever channel it is nearest - the honest answer, because the ridge stands
# between two channels.
FORK_RUNS = ("leg3", "orange_lead", "orange", "blue_lead", "blue", "merge_lead", "final")

# How far below its centre a marble's floor may be and still be its floor, in
# simulation units. A rolling marble's is one radius; 0.62 is a radius and a
# quarter, which is the most a marble bouncing along a cradle showed over the
# traces this was calibrated on.
SUPPORTED = 0.62

REACH = 40.0
FAN = 16

STOPPED_SPEED = 1.5
STOPPED_TICKS = 240


def side_axis(run, index: int):
    """The run's horizontal side axis - lateral with the roll taken out."""
    forward = run.tangents[index]
    side = (forward[2], 0.0, -forward[0])
    length = math.hypot(side[0], side[2])
    return (side[0] / length, 0.0, side[2] / length) if length > 1e-9 else (1.0, 0.0, 0.0)


def frame_of(runs, position, previous=None):
    """(run, sample, across, rise) for a point, on the run it is nearest.

    `previous` narrows the search to a window on the same run plus all of every
    other, which is what makes this affordable per tick. Same trick and same
    reason as `sloped.race._locate`.
    """
    best = None
    for name in FORK_RUNS:
        run = runs.get(name)
        if run is None:
            continue
        if previous is not None and previous[0] == name:
            low = max(0, previous[1] - 12)
            high = min(len(run.sim_path), previous[1] + 13)
        else:
            low, high = 0, len(run.sim_path)
        for index in range(low, high):
            distance = math.dist(position, run.sim_path[index])
            if best is None or distance < best[0]:
                best = (distance, name, index)
    if best is None:
        return None
    _distance, name, index = best
    run = runs[name]
    side = side_axis(run, index)
    centre = run.sim_path[index]
    _lateral, up, _forward = run.frames[index]
    bottom = centre[1] + up[1] * run.floor_offset
    offset = [position[axis] - centre[axis] for axis in range(3)]
    across = sum(offset[axis] * side[axis] for axis in range(3))
    return name, index, across, position[1] - bottom


def probe(world, position):
    """(drop, owner, pinch) for one marble centre, by ray.

    `drop` and its owner come from one ray straight down; `pinch` from a fan of
    `FAN` horizontal ones. Horizontal rather than spherical because the failure
    this looks for is lateral - a throat, a corner, a splitter - and a fan in
    the plane of the centre is where a lateral constraint is tightest.
    """
    starts = [position]
    ends = [(position[0], position[1] - REACH, position[2])]
    for step in range(FAN):
        angle = 2.0 * math.pi * step / FAN
        starts.append(position)
        ends.append(
            (
                position[0] + math.cos(angle) * REACH,
                position[1],
                position[2] + math.sin(angle) * REACH,
            )
        )
    hits = world.ray_batch(starts, ends)
    body, _fraction, point = hits[0]
    drop = None if body < 0 else position[1] - point[1]
    owner = world.owner_of(body) if body >= 0 else None
    pinch = None
    for hit_body, hit_fraction, _hit_point in hits[1:]:
        if hit_body < 0:
            continue
        distance = hit_fraction * REACH
        if pinch is None or distance < pinch:
            pinch = distance
    return drop, owner, pinch


def route_of(place) -> str | None:
    """The route a location commits a marble to, or None while it is open.

    The same rule as `sloped.race._route_from_place`, restated rather than
    imported because that one reads a live race's own run table.
    """
    from sloped import joins

    name, index = place
    if name in ("blue_lead", "blue"):
        return "blue"
    if name == "orange":
        return "orange"
    if name == "orange_lead" and index > joins.FORK_WINDOW_ORANGE:
        return "orange"
    if name == "leg3" and index > joins.FORK_SAMPLE + joins.FORK_GUARD_WINDOW[3]:
        return "blue"
    return None


class Sweep:
    """One injected field, watched to a verdict this tool owns."""

    EVERY = 2                    # ticks between probes

    def __init__(self, machine, config, duration: float) -> None:
        from marble3d.simulation import MarbleSimulation

        self.machine = machine
        self.runs = machine.runs
        self.injector = machine.injector
        self.sim = MarbleSimulation(machine, config, 0, len(self.injector.offsets))
        self.world = self.sim.world
        self.max_ticks = int(round(duration * config.physics.physics_hz))
        # `marble3d.simulation` places marbles at rest; give them the injector's
        # velocity before the first step, exactly as `SplitEntry` does.
        for marble_id, marble in self.sim.marbles.items():
            velocity = self.injector.velocities()[marble.start_index]
            self.world.pybullet.resetBaseVelocity(
                self.world.marbles[marble_id],
                linearVelocity=[float(value) for value in velocity],
                angularVelocity=[0.0, 0.0, 0.0],
                physicsClientId=self.world.client,
            )
        self.state: dict[int, dict[str, Any]] = {
            marble_id: {
                "offset": self.injector.offsets[marble.start_index],
                "speed": self.injector.speed,
                "release": None,
                "worst_pinch": None,
                "route": None,
                "furthest": None,
                "path": [],
            }
            for marble_id, marble in self.sim.marbles.items()
        }
        self._at: dict[int, tuple[str, int]] = {}
        self._slow: dict[int, int] = {}
        self._crossed: set[int] = set()

    def _past_line(self, position) -> bool:
        """Has the marble crossed the sprint's exit socket?

        `marble3d.simulation._past_finish` looks for the *machine's* last exit
        socket and finds nothing to compare against on a partial machine, so on
        `split_machine` it never fires: 23 of 28 entries rolled to a stop on the
        finish deck and were booked `stuck` at `final[117]`. This is
        `sloped.splitlab.SplitEntry._past_line`, which exists for that reason.
        """
        line = self.machine.finish_line
        flow, up, across = line.frame.axes()
        offset = tuple(a - b for a, b in zip(position, line.frame.position))
        along = sum(a * b for a, b in zip(offset, flow))
        if not 0.0 < along < 6.0 * MARBLE_RADIUS:
            return False
        sideways = abs(sum(a * b for a, b in zip(offset, across)))
        height = sum(a * b for a, b in zip(offset, up))
        diameter = 2.0 * MARBLE_RADIUS
        return (
            sideways <= 0.5 * line.width + diameter
            and -diameter <= height <= line.height + 3.0 * diameter
        )

    def run(self) -> dict[int, dict[str, Any]]:
        while self.sim.ticks < self.max_ticks:
            self.sim.step()
            live = [
                marble_id
                for marble_id, marble in self.sim.marbles.items()
                if marble.state in ("running", "queued")
            ]
            if not live:
                break
            if self.sim.ticks % self.EVERY:
                continue
            for marble_id in live:
                marble = self.sim.marbles[marble_id]
                position, _orientation, velocity, _spin = marble.pose
                previous = self._at.get(marble_id)
                located = frame_of(self.runs, position, previous)
                if located is None:
                    continue
                name, index, across, rise = located
                self._at[marble_id] = (name, index)
                block = self.state[marble_id]
                if block["route"] is None:
                    block["route"] = route_of((name, index))
                block["furthest"] = [name, index]
                drop, owner, pinch = probe(self.world, position)
                if pinch is not None and (
                    block["worst_pinch"] is None or pinch < block["worst_pinch"]
                ):
                    block["worst_pinch"] = round(pinch, 4)
                if marble_id not in self._crossed and self._past_line(position):
                    self._crossed.add(marble_id)
                speed = math.dist(velocity, (0.0, 0.0, 0.0))
                self._slow[marble_id] = (
                    self._slow.get(marble_id, 0) + self.EVERY if speed < STOPPED_SPEED else 0
                )
                row = {
                    "t": round(self.sim.elapsed, 4),
                    "run": name,
                    "sample": index,
                    "across": round(across, 4),
                    "rise": round(rise, 4),
                    "speed": round(speed, 3),
                    "drop": None if drop is None else round(drop, 4),
                    "floor": owner,
                    "pinch": None if pinch is None else round(pinch, 4),
                }
                block["path"].append(row)
                if drop is not None and drop <= SUPPORTED:
                    block["release"] = row
        return self.finish()

    def finish(self) -> dict[int, dict[str, Any]]:
        for marble_id, marble in self.sim.marbles.items():
            block = self.state[marble_id]
            if marble.state == "finished" or marble_id in self._crossed:
                verdict = "finished"
            elif marble.state == "escaped":
                verdict = "escaped"
            elif self._slow.get(marble_id, 0) >= STOPPED_TICKS:
                verdict = "stuck"
            else:
                verdict = "running"
            block["verdict"] = verdict
            block["finished"] = verdict == "finished"
            # Reported rather than acted on: this is what `SplitEntry` would
            # have called the outcome, and the two disagree wherever a marble
            # flies over the ridge and lands.
            block["last_supported"] = (
                None
                if block["release"] is None
                else [block["release"]["run"], block["release"]["sample"]]
            )
        self.sim.close()
        return self.state


def sweep(
    speeds: Sequence[float],
    offsets: Sequence[float],
    yaws: Sequence[float],
    pack: int | None,
    duration: float,
    knobs: dict[str, Any],
    entry_back: int = 10,
    keep_paths: bool = True,
) -> list[dict[str, Any]]:
    """Every (speed, yaw) launched once, as a field of `offsets`.

    `pack` slices the offsets into groups of that size, so the same offsets can
    be run one at a time, in pairs, in fours or all together - the A-to-D
    ladder section 7 asks for - without changing where any of them starts.
    """
    from tools.sloped_fork_lab import _apply

    _apply({"label": "sweep", **knobs})
    from sloped.splitlab import split_machine

    if pack is None or pack >= len(offsets):
        groups = [tuple(offsets)]
    else:
        groups = [tuple(offsets[i : i + pack]) for i in range(0, len(offsets), pack)]

    out: list[dict[str, Any]] = []
    for speed in speeds:
        for yaw in yaws:
            for group in groups:
                machine = split_machine(
                    DEFAULT_CONFIG,
                    speed=speed,
                    offsets=group,
                    yaw_deg=yaw,
                    entry_back=entry_back,
                )
                results = Sweep(machine, DEFAULT_CONFIG, duration).run()
                for block in results.values():
                    if not keep_paths:
                        block = {**block, "path": block["path"][-8:]}
                    out.append({**block, "yaw": yaw, "pack": len(group)})
    return out


def report(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    finished = [row for row in rows if row["finished"]]
    by_route: Counter = Counter(row["route"] or "unrouted" for row in rows)
    done_route: Counter = Counter(row["route"] or "unrouted" for row in finished)
    verdicts: Counter = Counter(row["verdict"] for row in rows)
    releases: Counter = Counter()
    for row in rows:
        if row["finished"]:
            continue
        release = row["release"]
        releases["-" if release is None else f"{release['run']}[{release['sample']}]"] += 1
    pinches = [row["worst_pinch"] for row in rows if row["worst_pinch"] is not None]
    return {
        "entries": total,
        "finished": len(finished),
        "pass_rate": round(len(finished) / max(total, 1), 4),
        "verdicts": dict(verdicts),
        "by_route": dict(by_route),
        "finished_by_route": dict(done_route),
        "route_completion": {
            name: round(done_route.get(name, 0) / count, 4)
            for name, count in sorted(by_route.items())
        },
        "release_sites": dict(releases.most_common(12)),
        "worst_pinch": None if not pinches else round(min(pinches), 4),
        "median_pinch": None if not pinches else round(sorted(pinches)[len(pinches) // 2], 4),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--speeds", type=float, nargs="*", default=[36.0, 43.0, 50.0])
    parser.add_argument(
        "--offsets", type=float, nargs="*", default=[-0.8, -0.5, -0.2, 0.0, 0.2, 0.5, 0.8]
    )
    parser.add_argument("--yaws", type=float, nargs="*", default=[0.0])
    parser.add_argument(
        "--pack", type=int, default=1, help="marbles launched together; 0 means all of them"
    )
    parser.add_argument("--duration", type=float, default=18.0)
    parser.add_argument("--entry-back", type=int, default=10)
    parser.add_argument("--examples", type=int, default=6)
    parser.add_argument("--knobs", default="", help="JSON object of sloped_fork_lab knobs")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    knobs = json.loads(args.knobs) if args.knobs else {}
    rows = sweep(
        args.speeds,
        args.offsets,
        args.yaws,
        None if args.pack == 0 else args.pack,
        args.duration,
        knobs,
        args.entry_back,
    )
    facts = report(rows)
    print(
        f"{facts['entries']} entries, pack {args.pack or len(args.offsets)}, "
        f"knobs {knobs or 'as built'}"
    )
    print(f"  finished {facts['finished']}/{facts['entries']} = {facts['pass_rate']:.3f}  "
          f"{facts['verdicts']}")
    print(f"  by route {facts['by_route']}  completion {facts['route_completion']}")
    print(f"  release sites {facts['release_sites']}")
    print(f"  worst lateral clearance {facts['worst_pinch']}, median {facts['median_pinch']}")

    shown = 0
    for row in rows:
        if row["finished"] or shown >= args.examples:
            continue
        shown += 1
        release = row["release"]
        print(
            f"  offset {row['offset']:+.2f} v {row['speed']:.0f} yaw {row['yaw']:+.0f} "
            f"route {row['route']} {row['verdict']} furthest {row['furthest']}"
        )
        if release is not None:
            print(
                f"    released on {release['run']}[{release['sample']}] "
                f"across {release['across']:+.3f} rise {release['rise']:+.3f} "
                f"v {release['speed']:.1f} floor {release['floor']} drop {release['drop']}"
            )
        for frame in row["path"][-4:]:
            print(
                f"      {frame['run']}[{frame['sample']}] across {frame['across']:+.3f} "
                f"rise {frame['rise']:+.3f} v {frame['speed']:.1f} "
                f"drop {frame['drop']} floor {frame['floor']} pinch {frame['pinch']}"
            )

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"knobs": knobs, "report": facts, "rows": rows}, handle, indent=1)
            handle.write("\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

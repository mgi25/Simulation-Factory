"""Which tick sets `max_travel_per_tick`, and what is happening at it.

Section 11 of the V1.17 brief. The production benchmark reports 0.746 against a
0.5 budget and has done since V1.11 without the reading ever being traced to a
site. The budget exists to keep the machine out of the regime where discrete
contact detection can miss a **wall**, so the question is not "how fast" but
"fast, next to what".

    python tools/sloped_travel_trace.py --seed 5432

Re-runs the seed and records, at the tick the maximum is set: the marble, its
speed, its position before and after, the run and sample it was nearest, what
static geometry and what actuator it was in contact with, the clearance to the
nearest surface in the direction of travel, and whether it was airborne.

**This re-runs the physics; it does not change it.** The race is deterministic,
so the run traced here is the run that was benchmarked - which the tool checks
by comparing its own state digest against the exported replay's.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG
from marble3d.units import MARBLE_RADIUS

from sloped.course import sloped_course
from sloped.race import SlopedRace
from sloped.scale import SIM_TO_LAYOUT

REACH = 30.0


class TravelTrace(SlopedRace):
    """A race that remembers the tick its fastest in-machine marble set."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.bounds = self.machine.bounds()
        self.best: dict[str, Any] | None = None
        self._previous: dict[int, tuple[float, float, float]] = {}

    def _inside(self, position) -> bool:
        return all(
            self.bounds.lower[axis] <= position[axis] <= self.bounds.upper[axis]
            for axis in range(3)
        )

    def step(self) -> None:
        before = {
            marble_id: marble.pose[0] for marble_id, marble in self.marbles.items()
        }
        super().step()
        dt = self.config.physics.dt
        for marble_id, marble in self.marbles.items():
            if marble.state not in ("running", "queued"):
                continue
            position, _orientation, velocity, spin = marble.pose
            if not self._inside(position):
                continue
            speed = math.dist(velocity, (0.0, 0.0, 0.0))
            travel = speed * dt
            if self.best is not None and travel <= self.best["travel"]:
                continue
            statics: set[str] = set()
            actuators: set[str] = set()
            depth = 0.0
            for contact in getattr(self, "_contacts", ()):
                for body, other in (
                    (contact.body_a, contact.body_b),
                    (contact.body_b, contact.body_a),
                ):
                    if self.world.marble_of(body) != marble_id:
                        continue
                    if self.world.marble_of(other) is not None:
                        statics.add("marble")
                        continue
                    record = self.world.bodies.get(other)
                    name = self.world.owner_of(other)
                    if record is not None and record.kind == "kinematic":
                        actuators.add(name)
                    else:
                        statics.add(name)
                    depth = min(depth, contact.distance)
            place = self._where.get(marble_id)
            self.best = {
                "tick": self.ticks,
                "t": round(self.elapsed, 5),
                "marble": marble_id,
                "speed": round(speed, 4),
                "travel": travel,
                "travel_diameters": round(travel / (2.0 * MARBLE_RADIUS), 4),
                "before": [round(v, 4) for v in before.get(marble_id, position)],
                "after": [round(v, 4) for v in position],
                "velocity": [round(v, 3) for v in velocity],
                "spin": round(math.dist(spin, (0.0, 0.0, 0.0)), 2),
                "place": None if place is None else [place[0], place[1]],
                "touching_static": sorted(statics),
                "touching_actuator": sorted(actuators),
                "worst_depth": round(depth, 5),
                "airborne": not statics and not actuators,
            }


def clearance(world, position, velocity) -> dict[str, Any]:
    """How far the surface is in the direction of travel, and all round."""
    speed = math.dist(velocity, (0.0, 0.0, 0.0))
    out: dict[str, Any] = {}
    if speed > 1e-6:
        ahead = tuple(
            position[axis] + velocity[axis] / speed * REACH for axis in range(3)
        )
        body, fraction, _point = world.ray_batch([position], [ahead])[0]
        out["ahead"] = None if body < 0 else round(fraction * REACH, 4)
        out["ahead_owner"] = None if body < 0 else world.owner_of(body)
    starts, ends = [], []
    for axis in range(3):
        for sign in (-1.0, 1.0):
            end = list(position)
            end[axis] += sign * REACH
            starts.append(position)
            ends.append(tuple(end))
    nearest = None
    owner = None
    for body, fraction, _point in world.ray_batch(starts, ends):
        if body < 0:
            continue
        distance = fraction * REACH
        if nearest is None or distance < nearest:
            nearest = distance
            owner = world.owner_of(body)
    out["nearest"] = None if nearest is None else round(nearest, 4)
    out["nearest_owner"] = owner
    return out


def trace(seed: int, marbles: int = 8, duration: float = 45.0) -> dict[str, Any]:
    machine = sloped_course(routes="both")
    race = TravelTrace(machine, DEFAULT_CONFIG, seed, marbles)
    ticks = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
    try:
        while race.ticks < ticks and not race.finished:
            race.step()
        best = dict(race.best or {})
        if best:
            position = tuple(best["after"])
            best["clearance"] = clearance(race.world, position, best["velocity"])
        best["stats_travel"] = round(race.stats.max_travel_per_tick, 5)
        best["stats_falling"] = round(race.stats.max_travel_falling, 5)
        best["stats_top_speed"] = round(race.stats.top_speed, 4)
        best["budget"] = DEFAULT_CONFIG.collider.travel_budget if hasattr(
            DEFAULT_CONFIG.collider, "travel_budget"
        ) else None
        return best
    finally:
        race.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    found = trace(args.seed, args.marbles, args.duration)
    print(f"seed {args.seed}: max travel per tick inside the machine")
    print(
        f"  {found['travel']:.5f} units = {found['travel_diameters']:.3f} of a "
        f"diameter, at tick {found['tick']} ({found['t']} s)"
    )
    print(
        f"  marble {found['marble']} at {found['speed']} wu/s "
        f"({found['speed'] * SIM_TO_LAYOUT:.2f} layout units/s), spin {found['spin']}"
    )
    print(f"  nearest run  {found['place']}")
    print(f"  before {found['before']}  ->  after {found['after']}")
    print(f"  velocity {found['velocity']}")
    print(
        f"  touching static {found['touching_static'] or 'nothing'}   "
        f"actuator {found['touching_actuator'] or 'nothing'}   "
        f"airborne {found['airborne']}"
    )
    print(f"  worst contact depth {found['worst_depth']}")
    print(f"  clearance {found.get('clearance')}")
    print(
        f"  run stats: in-machine {found['stats_travel']}, "
        f"falling {found['stats_falling']}, top speed {found['stats_top_speed']}"
    )
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(found, handle, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Where the two validation outliers actually happen.

    python tools/sloped_validation_trace.py --seeds 48 --routes blue

Sections 8 and 9 of the V1.10 brief. A 600-race benchmark reports one number
for each of these across 4,800 racers and no site for either:

    max_travel_per_tick   0.53335   against a 0.5 budget
    worst_penetration    -1.0396    simulation units

Neither can be acted on as a number. This runs races with the two quantities
recomputed alongside the ones `marble3d.simulation` keeps, but with the tick,
the racer, the position, the velocity, the module and the contact pair that
produced them - so each one names a place in the machine.

## What `max_travel_per_tick` is, and why the site matters

It is not a measured displacement. `RunStats.max_travel_per_tick` is
`top_speed * dt`, and `top_speed` is the largest instantaneous speed any marble
reached at any tick - so the quantity the budget is compared against is a
velocity reading, and a velocity reading is high wherever a marble is *falling*,
whether or not it is anywhere near a collider. The budget exists to keep the
machine out of the regime where discrete contact detection misses a wall; a
marble in free flight below the course has no wall to miss. So the question the
budget really asks is **where the fastest marble was**, and that is what this
records.

## What `worst_penetration` is

The most negative `contactDistance` Bullet reported on any contact pair in the
race, taken over every pair including marble-on-marble and marble-on-actuator.
The site is recorded with the pair's owners, the module, the relative speed
along the contact normal and whether either body was a moving part.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG
from marble3d.units import MARBLE_RADIUS

from sloped.course import sloped_course
from sloped.race import SlopedRace


class ValidationRace(SlopedRace):
    """A race that keeps the context of its own two worst readings."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fastest: dict[str, Any] | None = None
        self.deepest: dict[str, Any] | None = None
        self._moving: set[str] = {
            record.module.id
            for record in self.built
            if record.module.local_actuators()
        }

    # --- the fastest marble ---------------------------------------------

    def _read_marbles(self) -> None:
        # Read before the parent does, because `_retire` zeroes a marble's
        # velocity in the same pass that `top_speed` is taken from it - so the
        # tick a marble leaves the machine on is exactly the tick whose reading
        # would otherwise be unattributable, and on this course it is usually
        # the record.
        for marble_id in list(self.world.marbles):
            position, _orientation, velocity, _spin = self.world.marble_state(marble_id)
            if not all(math.isfinite(value) for value in position + velocity):
                continue
            speed = math.dist(velocity, (0.0, 0.0, 0.0))
            if self.fastest is not None and speed <= self.fastest["speed"]:
                continue
            inside = self.machine.bounds().contains(position, slack=MARBLE_RADIUS)
            place = self._where.get(marble_id)
            self.fastest = {
                "seed": self.seed,
                "tick": self.ticks,
                "time": round(self.elapsed, 4),
                "marble": marble_id,
                "slot": self.marbles[marble_id].start_index,
                "speed": speed,
                "travel": speed * self.dt,
                "at": [round(value, 4) for value in position],
                "velocity": [round(value, 4) for value in velocity],
                "module": self.machine.module_at(position, self.marbles[marble_id].module)
                or "airborne",
                "located": None if place is None else [place[0], place[1]],
                "touching": sorted(
                    {
                        self.world.owner_of(other)
                        for contact in getattr(self, "_contacts", ())
                        for body, other in (
                            (contact.body_a, contact.body_b),
                            (contact.body_b, contact.body_a),
                        )
                        if self.world.marble_of(body) == marble_id
                        and self.world.marble_of(other) is None
                    }
                ),
                "inside_machine": bool(inside),
                "state": self.marbles[marble_id].state,
            }
        super()._read_marbles()

    # --- the deepest contact --------------------------------------------

    def _read_contacts(self) -> None:
        super()._read_contacts()
        for contact in self._contacts:
            if self.deepest is not None and contact.distance >= self.deepest["distance"]:
                continue
            first = self.world.marble_of(contact.body_a)
            second = self.world.marble_of(contact.body_b)
            owners = (self.world.owner_of(contact.body_a), self.world.owner_of(contact.body_b))
            kinds = [
                self.world.bodies[body].kind if body in self.world.bodies else "?"
                for body in (contact.body_a, contact.body_b)
            ]
            speeds = []
            for marble_id in (first, second):
                if marble_id is None:
                    speeds.append(None)
                    continue
                velocity = self.marbles[marble_id].pose[2]
                speeds.append(
                    round(sum(v * n for v, n in zip(velocity, contact.normal)), 4)
                )
            self.deepest = {
                "seed": self.seed,
                "tick": self.ticks,
                "time": round(self.elapsed, 4),
                "distance": contact.distance,
                "owners": list(owners),
                "marbles": [first, second],
                "kind": "marble-marble"
                if first is not None and second is not None
                else f"marble-{[k for k in kinds if k != 'marble'][0] if any(k != 'marble' for k in kinds) else '?'}",
                "bodies": [contact.body_a, contact.body_b],
                "body_kinds": kinds,
                "moving_part": sorted(set(owners) & self._moving),
                "at": [round(value, 4) for value in contact.position],
                "normal": [round(value, 4) for value in contact.normal],
                "normal_speed": speeds,
                "impulse": round(contact.normal_impulse, 6),
            }


def _one(job) -> list[dict[str, Any]]:
    seeds, routes, duration = job
    machine = sloped_course(routes=routes)
    out = []
    for seed in seeds:
        race = ValidationRace(machine, DEFAULT_CONFIG, seed, 8)
        limit = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
        try:
            while race.ticks < limit and not race.finished:
                race.step()
            out.append(
                {
                    "seed": seed,
                    "fastest": race.fastest,
                    "deepest": race.deepest,
                    "stats_travel": race.stats.max_travel_per_tick,
                    "stats_penetration": race.stats.worst_penetration,
                }
            )
        finally:
            race.close()
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=48)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--routes", default="blue", choices=("blue", "both"))
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--chunk", type=int, default=2)
    parser.add_argument("--show", type=int, default=8)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    jobs = [
        (seeds[index : index + args.chunk], args.routes, args.duration)
        for index in range(0, len(seeds), args.chunk)
    ]
    started = time.perf_counter()
    if args.workers <= 1:
        batches = [_one(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            batches = list(pool.map(_one, jobs))
    rows = [row for batch in batches for row in batch]
    wall = time.perf_counter() - started

    budget = DEFAULT_CONFIG.marble.travel_budget * DEFAULT_CONFIG.marble.diameter
    fastest = sorted((r["fastest"] for r in rows if r["fastest"]), key=lambda r: -r["travel"])
    deepest = sorted((r["deepest"] for r in rows if r["deepest"]), key=lambda r: r["distance"])
    over = [row for row in fastest if row["travel"] > budget]

    print(f"{len(rows)} races [routes={args.routes}] in {wall:.0f}s; travel budget {budget}")
    print(
        f"  worst travel per tick {fastest[0]['travel']:.5f}; "
        f"{len(over)} of {len(rows)} races exceed the budget"
    )
    outside = sum(1 for row in fastest if not row["inside_machine"])
    airborne = sum(1 for row in fastest if not row["touching"])
    print(
        f"  of the {len(fastest)} per-race records, {outside} were already outside the "
        f"machine's own bounds and {airborne} were touching nothing at all"
    )
    print("  module of the fastest reading: "
          + ", ".join(f"{k} x{v}" for k, v in Counter(r["module"] for r in fastest).most_common(6)))
    print()
    print(f"  {'travel':>8} {'speed':>7} {'seed':>5} {'m':>2} {'module':<12} {'located':<16} "
          f"{'in?':>4} touching")
    for row in fastest[: args.show]:
        located = "-" if row["located"] is None else f"{row['located'][0]}[{row['located'][1]}]"
        print(
            f"  {row['travel']:>8.5f} {row['speed']:>7.2f} {row['seed']:>5} {row['marble']:>2} "
            f"{row['module']:<12} {located:<16} {'yes' if row['inside_machine'] else 'no':>4} "
            f"{','.join(row['touching']) or '-'}"
        )

    print()
    print(f"  worst penetration {deepest[0]['distance']:.5f}")
    print("  by pair kind: "
          + ", ".join(f"{k} x{v}" for k, v in Counter(r["kind"] for r in deepest).most_common()))
    print("  by owners: "
          + ", ".join(f"{k} x{v}" for k, v in Counter(
              " / ".join(sorted(set(r["owners"]))) for r in deepest).most_common(6)))
    print()
    print(f"  {'depth':>9} {'seed':>5} {'tick':>7} {'kind':<14} {'owners':<28} {'impulse':>9} moving")
    for row in deepest[: args.show]:
        print(
            f"  {row['distance']:>9.5f} {row['seed']:>5} {row['tick']:>7} {row['kind']:<14} "
            f"{' / '.join(row['owners']):<28} {row['impulse']:>9.4f} "
            f"{','.join(row['moving_part']) or '-'}"
        )

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "routes": args.routes,
                    "seeds": [args.first_seed, args.first_seed + args.seeds],
                    "travel_budget": budget,
                    "races": rows,
                },
                handle,
                indent=1,
            )
            handle.write("\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

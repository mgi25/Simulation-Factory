"""What happens to a racer at the fork, racer by racer.

Section 4 of the V1.10 brief: before any geometry moves, produce the failure
histogram and, for representative failures, the incoming lateral position and
velocity, the contact sequence through the fork, where it failed, and what it
was touching when it did.

    python tools/sloped_fork_trace.py --seeds 24 --out docs/validation/...

## The frame everything is reported in

leg3's own, at the sample the racer is nearest, but with the **roll taken out**
of the across axis: `across` is a horizontal distance east of leg3's centreline
and `rise` is height above leg3's cradle bottom, both in simulation units. That
is deliberate. Every existing account of the fork - `sloped.joins`,
`sloped.stations.ForkRidge` - is written in each channel's own banked profile
units, and the thing that decides whether a marble crosses is what the surface
looks like to **gravity**, which at a 26-degree bank is a different shape.

A marble is 1.0 simulation units across, so a clearance under 1.0 anywhere in
this report is a place a marble cannot go.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG

from sloped import joins
from sloped.course import sloped_course
from sloped.race import SlopedRace

# How far either side of the fork sample a racer counts as "at the fork".
WATCH_BACK = 12
WATCH_ON = 30


def side_axis(run, index: int):
    """The run's horizontal side axis - its lateral with the roll taken out."""
    forward = run.tangents[index]
    side = (forward[2], 0.0, -forward[0])
    length = math.hypot(side[0], side[2])
    return (side[0] / length, 0.0, side[2] / length) if length > 1e-9 else (1.0, 0.0, 0.0)


class ForkTrace(SlopedRace):
    """A race that writes down what every racer did in the fork window."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        leg3 = self.runs["leg3"]
        self.fork_point = leg3.sim_path[joins.FORK_SAMPLE]
        self.trace: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.touch_order: dict[int, list[str]] = defaultdict(list)
        self.entry: dict[int, dict[str, Any]] = {}

    def _frame_of(self, position):
        """(across, rise, sample) in leg3's gravity-aligned frame."""
        leg3 = self.runs["leg3"]
        low = max(0, joins.FORK_SAMPLE - WATCH_BACK - 8)
        high = min(len(leg3.sim_path), joins.FORK_SAMPLE + WATCH_ON + 8)
        best = min(
            ((math.dist(position, leg3.sim_path[i]), i) for i in range(low, high)),
            key=lambda pair: pair[0],
        )
        index = best[1]
        side = side_axis(leg3, index)
        centre = leg3.sim_path[index]
        _lateral, up, _forward = leg3.frames[index]
        bottom = centre[1] + up[1] * leg3.floor_offset
        offset = [position[axis] - centre[axis] for axis in range(3)]
        across = sum(offset[axis] * side[axis] for axis in range(3))
        return across, position[1] - bottom, index

    def step(self) -> None:
        super().step()
        for marble_id, marble in self.marbles.items():
            position, _orientation, velocity, _spin = marble.pose
            if math.dist(position, self.fork_point) > 26.0:
                continue
            across, rise, index = self._frame_of(position)
            step = index - joins.FORK_SAMPLE
            if not -WATCH_BACK <= step <= WATCH_ON:
                continue
            if marble_id not in self.entry and step >= -4:
                side = side_axis(self.runs["leg3"], index)
                self.entry[marble_id] = {
                    "step": step,
                    "across": round(across, 4),
                    "rise": round(rise, 4),
                    "speed": round(math.dist(velocity, (0.0, 0.0, 0.0)), 3),
                    "lateral_speed": round(sum(velocity[a] * side[a] for a in range(3)), 3),
                    "vertical_speed": round(velocity[1], 3),
                    "time": round(self.elapsed, 4),
                }
            if self.ticks % 4:
                continue
            hits = []
            for contact in getattr(self, "_contacts", ()):
                for body, other in (
                    (contact.body_a, contact.body_b),
                    (contact.body_b, contact.body_a),
                ):
                    if self.world.marble_of(body) != marble_id:
                        continue
                    owner = self.world.owner_of(other)
                    if self.world.marble_of(other) is not None:
                        owner = "marble"
                    hits.append((owner, contact.normal, contact.distance))
            owners = sorted({hit[0] for hit in hits})
            for owner in owners:
                order = self.touch_order[marble_id]
                if not order or order[-1] != owner:
                    order.append(owner)
            self.trace[marble_id].append(
                {
                    "t": round(self.elapsed, 4),
                    "step": step,
                    "across": round(across, 3),
                    "rise": round(rise, 3),
                    "speed": round(math.dist(velocity, (0.0, 0.0, 0.0)), 2),
                    "touch": owners,
                    "normal": [round(v, 3) for v in hits[0][1]] if hits else None,
                }
            )


def trace_seed(seed: int, marbles: int = 8, duration: float = 40.0) -> dict[str, Any]:
    machine = sloped_course(routes="both")
    race = ForkTrace(machine, DEFAULT_CONFIG, seed, marbles)
    max_ticks = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
    try:
        while race.ticks < max_ticks and not race.finished:
            race.step()
        rows = []
        for marble_id, result in sorted(race.results.items()):
            touch = race._last_touch.get(marble_id)
            state = (
                "finished"
                if result.finish_order is not None
                else ("escaped" if race.marbles[marble_id].state == "escaped" else "stuck")
            )
            rows.append(
                {
                    "seed": seed,
                    "marble": marble_id,
                    "slot": result.start_slot,
                    "route": result.route,
                    "state": state,
                    "lost_at": list(result.lost_at) if result.lost_at else None,
                    "last_touch": [touch[0], touch[1]] if touch else None,
                    "entry": race.entry.get(marble_id),
                    "touch_order": race.touch_order.get(marble_id, []),
                    "fork_trace": race.trace.get(marble_id, []),
                }
            )
        return {"seed": seed, "racers": rows}
    finally:
        race.close()


def _one(job):
    seed, marbles, duration = job
    return trace_seed(seed, marbles, duration)


def summarise(seeds: Sequence[dict[str, Any]]) -> dict[str, Any]:
    racers = [row for seed in seeds for row in seed["racers"]]
    by_route: Counter = Counter()
    by_outcome: Counter = Counter()
    sites: Counter = Counter()
    entry_by_fate: dict[str, list[float]] = defaultdict(list)
    peak_by_fate: dict[str, list[float]] = defaultdict(list)
    for row in racers:
        route = row["route"] or "unrouted"
        by_route[route] += 1
        fate = f"{route}/{row['state']}"
        by_outcome[fate] += 1
        if row["state"] != "finished" and row["last_touch"]:
            sites[f"{row['last_touch'][0]}[{row['last_touch'][1]}]"] += 1
        if row["entry"]:
            entry_by_fate[fate].append(row["entry"]["across"])
        if row["fork_trace"]:
            peak_by_fate[fate].append(max(f["across"] for f in row["fork_trace"]))

    def spread(values):
        values = sorted(values)
        return {
            "n": len(values),
            "mean": round(sum(values) / len(values), 3),
            "min": round(values[0], 3),
            "median": round(values[len(values) // 2], 3),
            "max": round(values[-1], 3),
        }

    return {
        "racers": len(racers),
        "by_route": dict(by_route),
        "by_outcome": dict(by_outcome),
        "loss_sites": dict(sites.most_common(20)),
        "entry_across_by_fate": {k: spread(v) for k, v in sorted(entry_by_fate.items())},
        "peak_across_by_fate": {k: spread(v) for k, v in sorted(peak_by_fate.items())},
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--examples", type=int, default=8)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    wanted = list(range(args.first_seed, args.first_seed + args.seeds))
    if args.workers <= 1:
        seeds = [trace_seed(seed, args.marbles, args.duration) for seed in wanted]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            seeds = list(pool.map(_one, [(s, args.marbles, args.duration) for s in wanted]))
    report = summarise(seeds)
    print(f"{report['racers']} racers over {args.seeds} seeds")
    print(f"  by route   {report['by_route']}")
    print(f"  by outcome {report['by_outcome']}")
    print(f"  loss sites {report['loss_sites']}")
    for title, key in (
        ("entry across", "entry_across_by_fate"),
        ("peak across", "peak_across_by_fate"),
    ):
        print(f"  {title} (horizontal, sim units) by fate:")
        for fate, block in report[key].items():
            print(
                f"    {fate:<18} n={block['n']:<4} mean {block['mean']:+.3f}  "
                f"median {block['median']:+.3f}  range {block['min']:+.3f} .. {block['max']:+.3f}"
            )

    print()
    print("representative failures:")
    shown = 0
    for seed in seeds:
        for row in seed["racers"]:
            if row["state"] == "finished" or shown >= args.examples:
                continue
            shown += 1
            entry = row["entry"] or {}
            print(
                f"  seed {row['seed']:>3} marble {row['marble']} slot {row['slot']} "
                f"route {row['route']} {row['state']} last touch {row['last_touch']}"
            )
            print(
                f"    entry: across {entry.get('across')} rise {entry.get('rise')} "
                f"speed {entry.get('speed')} lateral {entry.get('lateral_speed')}"
            )
            print(f"    touched: {' -> '.join(row['touch_order'])}")
            for frame in row["fork_trace"][-6:]:
                print(
                    f"      t={frame['t']:>8} step {frame['step']:>+4} "
                    f"across {frame['across']:>+6.3f} rise {frame['rise']:>+6.3f} "
                    f"v {frame['speed']:>6.2f} touch {frame['touch']} n {frame['normal']}"
                )

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"summary": report, "seeds": seeds}, handle, indent=1)
            handle.write("\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""What happens to a racer at the merge and the sprint's first samples.

Section 4 of the V1.15 brief. `tools/sloped_fork_trace.py` is the same
instrument aimed at the fork; this one is aimed at `final[0..15]`, and it
reports in the **sprint's own gravity-aligned frame** rather than in any run's
banked profile units:

    along    simulation units down the sprint from `final[0]`'s centreline
             surface point, so `along / 0.3259` is the sprint's sample number
    across   horizontal, positive east - the side orange arrives from
    rise     world height above the sprint's own cradle bottom at that `along`

A marble is 1.0 simulation units across, so any clearance under 1.0 in this
report is a place a marble cannot be.

For every racer that does not finish it records the resting pose, every static
collider in contact with it and the normal and depth of each, the downward drop
and the lateral pinch, and a 30 Hz trajectory through the window. For every
racer it records the **arrival envelope** - where, how fast and at what angle it
entered the window - so section 7's "design for the corridor orange actually
uses" has numbers on both sides of it.

    python tools/sloped_final_trace.py --seeds 50 --first-seed 3301
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

from sloped.course import sloped_course
from sloped.race import SlopedRace
from tools.sloped_fork_sweep import probe
from tools.sloped_final_shoulder import datum, frame

# The window, in the sprint's own frame.
ALONG_BACK = -7.0
ALONG_ON = 9.0
ACROSS_REACH = 7.0
SAMPLE_EVERY = 8               # ticks between trajectory samples, 240 Hz / 8


class FinalTrace(SlopedRace):
    """A race that writes down what every racer did at the merge."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        final = self.runs["final"]
        self.spacing = math.dist(final.sim_path[0], final.sim_path[1])
        self._origin, self._forward, self._side = frame(final)
        self._final = final
        self.path: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.arrival: dict[int, dict[str, Any]] = {}
        self.last: dict[int, dict[str, Any]] = {}
        self.deepest: dict[int, float] = {}

    def local(self, point) -> tuple[float, float, float]:
        offset = [point[axis] - self._origin[axis] for axis in range(3)]
        along = sum(offset[axis] * self._forward[axis] for axis in range(3))
        across = sum(offset[axis] * self._side[axis] for axis in range(3))
        return along, across, point[1] - datum(self._final, along)

    def _vector(self, vector) -> tuple[float, float, float]:
        return (
            sum(vector[axis] * self._forward[axis] for axis in range(3)),
            sum(vector[axis] * self._side[axis] for axis in range(3)),
            vector[1],
        )

    def _static_contacts(self, marble_id: int):
        """Every collider touching this marble, with its normal and depth."""
        out = []
        for contact in getattr(self, "_contacts", ()):
            for body, other in (
                (contact.body_a, contact.body_b),
                (contact.body_b, contact.body_a),
            ):
                if self.world.marble_of(body) != marble_id:
                    continue
                if self.world.marble_of(other) is not None:
                    out.append(("marble", contact.normal, contact.distance))
                    continue
                out.append((self.world.owner_of(other), contact.normal, contact.distance))
        return out

    def step(self) -> None:
        super().step()
        if self.ticks % 2:
            return
        for marble_id, marble in self.marbles.items():
            if marble.state not in ("running", "queued"):
                continue
            position, _orientation, velocity, spin = marble.pose
            along, across, rise = self.local(position)
            if not (ALONG_BACK <= along <= ALONG_ON and abs(across) <= ACROSS_REACH):
                continue
            contacts = self._static_contacts(marble_id)
            speed = math.dist(velocity, (0.0, 0.0, 0.0))
            forward, sideways, vertical = self._vector(velocity)
            row = {
                "t": round(self.elapsed, 3),
                "along": round(along, 3),
                "sample": round(along / self.spacing, 2),
                "across": round(across, 3),
                "rise": round(rise, 3),
                "speed": round(speed, 2),
                "v": [round(forward, 2), round(sideways, 2), round(vertical, 2)],
                "spin": round(math.dist(spin, (0.0, 0.0, 0.0)), 1),
                "touch": sorted({name for name, _n, _d in contacts}),
            }
            if marble_id not in self.arrival:
                self.arrival[marble_id] = dict(row)
            self.last[marble_id] = dict(
                row,
                contacts=[
                    {
                        "owner": name,
                        "normal": [round(v, 3) for v in normal],
                        "depth": round(depth, 4),
                    }
                    for name, normal, depth in contacts
                ],
            )
            self.deepest[marble_id] = max(self.deepest.get(marble_id, -99.0), along)
            if self.ticks % SAMPLE_EVERY == 0:
                self.path[marble_id].append(row)


def _finish(race: FinalTrace, seed: int) -> list[dict[str, Any]]:
    rows = []
    for marble_id, result in sorted(race.results.items()):
        touch = race._last_touch.get(marble_id)
        state = (
            "finished"
            if result.finish_order is not None
            else ("escaped" if race.marbles[marble_id].state == "escaped" else "stuck")
        )
        rest = race.last.get(marble_id)
        if rest is not None and state != "finished":
            position, _orientation, _velocity, _spin = race.marbles[marble_id].pose
            drop, owner, pinch = probe(race.world, position)
            rest = dict(
                rest,
                drop=None if drop is None else round(drop, 4),
                drop_owner=owner,
                pinch=None if pinch is None else round(pinch, 4),
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
                "arrival": race.arrival.get(marble_id),
                "rest": rest,
                "furthest": round(race.deepest.get(marble_id, -99.0), 3),
                "path": race.path.get(marble_id, []) if state != "finished" else [],
            }
        )
    return rows


def trace_seed(seed: int, marbles: int = 8, duration: float = 40.0) -> dict[str, Any]:
    machine = sloped_course(routes="both")
    race = FinalTrace(machine, DEFAULT_CONFIG, seed, marbles)
    max_ticks = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
    try:
        while race.ticks < max_ticks and not race.finished:
            race.step()
        return {"seed": seed, "racers": _finish(race, seed)}
    finally:
        race.close()


def _one(job):
    return trace_seed(*job)


def spread(values):
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "min": round(values[0], 2),
        "p25": round(values[len(values) // 4], 2),
        "median": round(values[len(values) // 2], 2),
        "p75": round(values[3 * len(values) // 4], 2),
        "max": round(values[-1], 2),
    }


def summarise(seeds: Sequence[dict[str, Any]]) -> dict[str, Any]:
    racers = [row for seed in seeds for row in seed["racers"]]
    outcome: Counter = Counter()
    sites: Counter = Counter()
    rest_sample: Counter = Counter()
    rest_floor: Counter = Counter()
    envelope: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in racers:
        route = row["route"] or "unrouted"
        outcome[f"{route}/{row['state']}"] += 1
        if row["state"] != "finished" and row["last_touch"]:
            sites[f"{row['last_touch'][0]}[{row['last_touch'][1]}]"] += 1
        if row["state"] != "finished" and row["rest"]:
            rest = row["rest"]
            rest_sample[f"f[{int(round(rest['sample']))}]"] += 1
            rest_floor["+".join(rest["touch"]) or "-"] += 1
        if row["arrival"]:
            key = f"{route}/{'fin' if row['state'] == 'finished' else 'lost'}"
            envelope[key]["across"].append(row["arrival"]["across"])
            envelope[key]["rise"].append(row["arrival"]["rise"])
            envelope[key]["speed"].append(row["arrival"]["speed"])
            envelope[key]["sample"].append(row["arrival"]["sample"])
            forward, sideways, _vertical = row["arrival"]["v"]
            envelope[key]["angle"].append(round(math.degrees(math.atan2(sideways, forward)), 1))
    return {
        "racers": len(racers),
        "by_outcome": dict(outcome),
        "loss_sites": dict(sites.most_common(16)),
        "rest_sample": dict(rest_sample.most_common(16)),
        "rest_floor": dict(rest_floor.most_common(12)),
        "arrival_envelope": {
            key: {field: spread(values) for field, values in sorted(fields.items())}
            for key, fields in sorted(envelope.items())
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=24)
    parser.add_argument("--first-seed", type=int, default=3301)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--examples", type=int, default=6)
    parser.add_argument("--frames", type=int, default=14)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    wanted = list(range(args.first_seed, args.first_seed + args.seeds))
    jobs = [(seed, args.marbles, args.duration) for seed in wanted]
    if args.workers <= 1:
        seeds = [trace_seed(*job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            seeds = list(pool.map(_one, jobs))

    report = summarise(seeds)
    print(f"{report['racers']} racers over {args.seeds} seeds from {args.first_seed}")
    print(f"  by outcome  {report['by_outcome']}")
    print(f"  loss sites  {report['loss_sites']}")
    print(f"  rest sample {report['rest_sample']}")
    print(f"  rest floor  {report['rest_floor']}")
    print("\n  arrival envelope, in the sprint's frame")
    for key, fields in report["arrival_envelope"].items():
        print(f"    {key:<18}" + "  ".join(
            f"{field} {value['min']}..{value['max']} (med {value['median']})"
            for field, value in fields.items()
        ))

    losers = [
        row
        for seed in seeds
        for row in seed["racers"]
        if row["state"] != "finished" and row["rest"]
    ]
    losers.sort(key=lambda row: abs(row["rest"]["sample"] - 10.0))
    print(f"\n  {len(losers)} non-finishers reached the window; nearest {args.examples} to f[10]:")
    for row in losers[: args.examples]:
        rest = row["rest"]
        print(
            f"\n  seed {row['seed']} marble {row['marble']} slot {row['slot']} "
            f"{row['route']}/{row['state']}  last_touch {row['last_touch']}"
        )
        print(
            f"    rest  f[{rest['sample']}] across {rest['across']:+.3f} rise {rest['rise']:+.3f} "
            f"speed {rest['speed']} v {rest['v']} spin {rest['spin']} "
            f"drop {rest['drop']} ({rest['drop_owner']}) pinch {rest['pinch']}"
        )
        for contact in rest["contacts"]:
            print(
                f"      touching {contact['owner']:<12} normal {contact['normal']} "
                f"depth {contact['depth']}"
            )
        tail = row["path"][-args.frames :]
        for frame_row in tail:
            print(
                f"      t {frame_row['t']:>7} f[{frame_row['sample']:>6}] "
                f"across {frame_row['across']:+7.3f} rise {frame_row['rise']:+7.3f} "
                f"speed {frame_row['speed']:>6} v {frame_row['v']} {frame_row['touch']}"
            )

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"report": report, "seeds": seeds}, handle, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

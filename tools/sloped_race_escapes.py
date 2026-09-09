"""Where the full course loses the field, and with what - the whole route.

    python tools/sloped_race_escapes.py --seeds 24
    python tools/sloped_race_escapes.py --seeds 24 --routes blue
    python tools/sloped_race_escapes.py --seeds 48 --json out.json

`tools/sloped_escape_trace.py` does this for the start lab, which carries only
the launch and leg1. The full course adds leg2, leg3, the fork, both leads,
both lobes, the merge and the sprint - and the benchmark's own loss-site
histogram says that is where the racers actually go: 22.9% of them leave the
course, and `orange_lead[0]` alone accounts for more of it than every start
site put together.

A histogram cannot say whether a racer went over a rail, off the end of a
surface, or through a gap between two modules, and those are three different
repairs. So this records, at the tick the containment verdict fires: the run and
sample, how far across as a fraction of the local half width, how high above
the local floor against that sample's own containment, the speed and its
lateral and vertical components, and the local bank. Plus the route the racer
had been sorted onto, because a loss on `orange_lead` from a marble that was
never going to make the turn is a different fact from one that was.
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marble3d.config import DEFAULT_CONFIG  # noqa: E402
from sloped.course import sloped_course  # noqa: E402
from marble3d.simulation import STATE_ESCAPED  # noqa: E402
from sloped.race import LATERAL_SLACK, VERTICAL_SLACK, SlopedRace  # noqa: E402
from sloped.scale import SIM_TO_LAYOUT  # noqa: E402


class EscapeRace(SlopedRace):
    """A race that says *how* each racer left, not just where.

    `_containment` is overridden rather than copied so the base class keeps
    deciding the verdict and this only records the state at the moment it does.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.escapes: dict[int, dict] = {}
        self.peak_height: dict[int, float] = {}
        self.peak_reach: dict[int, float] = {}

    def _containment(self, marble_id, position):
        # **`RacerResult.state` is not set during the race.** It keeps its
        # "running" default until `run_race` assigns it at the end, so a gate
        # written against it never fires - the first version of this tool
        # reported 0 finished and 0 escaped over 176 racers while the benchmark
        # reported 74% finishing the same course. What the simulation does set
        # per tick is `_Marble.state`, and what the race sets is
        # `RacerResult.finish_order`, so those are the two facts read here.
        place = self._where.get(marble_id)
        already = marble_id in self.escapes
        before = self.results[marble_id].lost_at
        super()._containment(marble_id, position)
        fired = before is None and self.results[marble_id].lost_at is not None
        if place is None:
            return
        name, index = place
        run = self.runs.get(name)
        if run is None:
            return
        lateral, up, forward = run.frames[index]
        centre = run.sim_path[index]
        offset = [position[axis] - centre[axis] for axis in range(3)]
        across = sum(offset[axis] * lateral[axis] for axis in range(3))
        height = sum(offset[axis] * up[axis] for axis in range(3))
        half = 0.5 * run.clear_width * run.widths[index]
        ceiling = run.containment_at(index)
        self.peak_height[marble_id] = max(
            self.peak_height.get(marble_id, -9.9), height * SIM_TO_LAYOUT
        )
        self.peak_reach[marble_id] = max(
            self.peak_reach.get(marble_id, 0.0), abs(across) / max(half, 1e-9)
        )
        if already or not fired:
            return
        velocity = self.marbles[marble_id].pose[2]
        across_v = sum(velocity[axis] * lateral[axis] for axis in range(3))
        up_v = sum(velocity[axis] * up[axis] for axis in range(3))
        self.escapes[marble_id] = {
            "run": name,
            "sample": index,
            "pct": round(100.0 * index / max(len(run.sim_path) - 1, 1), 1),
            "slot": self.results[marble_id].start_slot,
            "route": self.results[marble_id].route,
            "state": self.marbles[marble_id].state,
            "at": [round(value, 4) for value in position],
            "reach": round(across / max(half, 1e-9), 4),
            "height": round(height * SIM_TO_LAYOUT, 4),
            "ceiling": round(ceiling * SIM_TO_LAYOUT, 4),
            "over_by": round((height - ceiling) * SIM_TO_LAYOUT, 4),
            "speed": round(math.hypot(*velocity) * SIM_TO_LAYOUT, 3),
            "across_speed": round(across_v * SIM_TO_LAYOUT, 3),
            "up_speed": round(up_v * SIM_TO_LAYOUT, 3),
            "bank_deg": round(math.degrees(run.banks[index]), 2),
            "which_test": self.results[marble_id].lost_how,
            "above_rail": bool(height > ceiling),
        }


def _one(job):
    seeds, routes, duration = job
    global _MACHINE
    try:
        cache = _MACHINE
    except NameError:
        cache = _MACHINE = {}
    machine = cache.get(routes)
    if machine is None:
        from sloped.course import sloped_course as build

        cache.clear()
        machine = cache[routes] = build(routes=routes)
    out = []
    for seed in seeds:
        race = EscapeRace(machine, DEFAULT_CONFIG, seed, 8)
        limit = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
        try:
            # `SlopedRace` exposes `finished` rather than a `settled()`, and
            # `run_race` drives it exactly this way.
            while race.ticks < limit and not race.finished:
                race.step()
            out.append({
                "seed": seed,
                "escapes": list(race.escapes.values()),
                "peak_height": max(race.peak_height.values(), default=-9.9),
                "peak_reach": max(race.peak_reach.values(), default=0.0),
                # `finish_order` is set by the race as each marble crosses,
                # unlike `state`, which `run_race` assigns afterwards.
                "finished": sum(
                    1 for r in race.results.values() if r.finish_order is not None
                ),
            })
        finally:
            race.close()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=24)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--routes", default="both", choices=("blue", "both"))
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--chunk", type=int, default=2)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--label", default="")
    args = parser.parse_args(argv)

    probe = sloped_course(routes=args.routes)
    for module in probe:
        getattr(module, "local_colliders", list)()

    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    chunks = [seeds[i:i + args.chunk] for i in range(0, len(seeds), args.chunk)]
    jobs = [(chunk, args.routes, args.duration) for chunk in chunks]
    started = time.perf_counter()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            batches = list(pool.map(_one, jobs))
    else:
        batches = [_one(job) for job in jobs]
    results = [row for batch in batches for row in batch]
    wall = time.perf_counter() - started

    escapes = [row for result in results for row in result["escapes"]]
    racers = 8 * len(results)
    finished = sum(result["finished"] for result in results)
    print(
        f"{args.label or 'race escapes'} [routes={args.routes}]: "
        f"{len(results)} races, {racers} racers in {wall:.1f}s"
    )
    print(
        f"  finished {finished} ({100.0 * finished / racers:.2f}%), "
        f"{len(escapes)} left the course ({100.0 * len(escapes) / racers:.2f}%)"
    )
    if escapes:
        by_site = Counter(f"{row['run']}[{row['sample']}]" for row in escapes)
        by_run = Counter(row["run"] for row in escapes)
        print("  by run: " + ", ".join(f"{k} x{v}" for k, v in by_run.most_common()))
        print("  worst sites: "
              + ", ".join(f"{k} x{v}" for k, v in by_site.most_common(8)))
        above = sum(1 for row in escapes if row["above_rail"])
        print(f"  {above} of {len(escapes)} were above the rail's top when the "
              f"verdict fired; {len(escapes) - above} were below it")
        tests = Counter(row["which_test"] for row in escapes)
        print("  the test that fired first: "
              + ", ".join(f"{k} x{v}" for k, v in tests.most_common()))
        print()
        header = ("  run           sample   %  slot route  | reach  height "
                  "ceiling  over | speed across    up | bank")
        print(header)
        print("  " + "-" * (len(header) - 2))
        shown = sorted(escapes, key=lambda r: (r["run"], r["sample"]))
        for row in shown[:40]:
            print(
                f"  {row['run']:<13} {row['sample']:5}{row['pct']:6.1f} "
                f"{row['slot']:4} {str(row['route'] or '-'):6} | "
                f"{row['reach']:+.2f}  {row['height']:+.3f} "
                f"{row['ceiling']:7.3f} {row['over_by']:+.3f} | "
                f"{row['speed']:5.1f} {row['across_speed']:+6.1f} "
                f"{row['up_speed']:+5.1f} | {row['bank_deg']:+5.1f}"
            )
        if len(shown) > 40:
            print(f"  ... and {len(shown) - 40} more")
        print("  " + "-" * (len(header) - 2))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "routes": args.routes,
                    "label": args.label,
                    "seeds": [args.first_seed, args.first_seed + args.seeds],
                    "racers": racers,
                    "finished": finished,
                    "escapes": escapes,
                    "wall_seconds": round(wall, 2),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Where on orange's lobe the field rides, and where it leaves.

The V1.15 200-seed gate's leading loss site is orange's own lobe - `orange[20]`
ten and `orange_lead[0]` six of twenty seven non-finishers, and the failure is
an **escape** rather than a jam. That is the shape `sloped.course.GUARD_BOOSTS`
was written for on the launch and on leg1 and leg2, and this is the instrument
that measured those: per sample, how high above the local floor the field runs
as a fraction of the run's own containment, and how far across as a fraction of
its half width.

    python tools/sloped_orange_trace.py --seeds 40 --first-seed 4001

A racer whose centre is above containment and outside the rail's face has gone
over the top. A histogram of loss sites cannot tell that from a racer that was
already outside the channel when the instrument first located it, and the two
are different repairs.

**Peaks are reported for the whole field, not only for the losers.** A field
running at 90% of the guard everywhere is one bad seed from a loss, and that is
invisible in a loss histogram.
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

WATCHED = ("orange_lead", "orange", "leg3", "blue_lead", "blue")


class OrangeTrace(SlopedRace):
    """A race that records how high and how wide the field runs on each branch."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # (run, sample) -> [max height fraction, max across fraction, count]
        self.ride: dict[tuple[str, int], list[float]] = defaultdict(
            lambda: [-9.0, 0.0, 0.0]
        )
        self.peak: dict[int, dict[str, Any]] = {}
        self.last: dict[int, dict[str, Any]] = {}

    def step(self) -> None:
        super().step()
        if self.ticks % 2:
            return
        for marble_id, marble in self.marbles.items():
            if marble.state not in ("running", "queued"):
                continue
            place = self._where.get(marble_id)
            if place is None:
                continue
            name, index = place
            if name not in WATCHED:
                continue
            position, _orientation, velocity, _spin = marble.pose
            run = self.runs[name]
            lateral, up, _forward = run.frames[index]
            centre = run.sim_path[index]
            offset = [position[axis] - centre[axis] for axis in range(3)]
            across = sum(offset[axis] * lateral[axis] for axis in range(3))
            height = sum(offset[axis] * up[axis] for axis in range(3))
            half = 0.5 * run.clear_width * run.widths[index]
            ceiling = run.containment_at(index)
            # Height is measured from the run's own floor rather than from its
            # centreline, because `containment_at` is measured from the floor.
            rise = (height - run.floor_offset) / max(ceiling - run.floor_offset, 1e-6)
            reach = abs(across) / max(half, 1e-6)
            cell = self.ride[(name, index)]
            cell[0] = max(cell[0], rise)
            cell[1] = max(cell[1], reach)
            cell[2] += 1
            row = {
                "run": name,
                "sample": index,
                "rise": round(rise, 4),
                "reach": round(reach, 4),
                "speed": round(math.dist(velocity, (0.0, 0.0, 0.0)), 2),
                "t": round(self.elapsed, 3),
            }
            self.last[marble_id] = row
            best = self.peak.get(marble_id)
            if best is None or rise > best["rise"]:
                self.peak[marble_id] = row


def trace_seed(seed: int, marbles: int = 8, duration: float = 40.0) -> dict[str, Any]:
    machine = sloped_course(routes="both")
    race = OrangeTrace(machine, DEFAULT_CONFIG, seed, marbles)
    max_ticks = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
    try:
        while race.ticks < max_ticks and not race.finished:
            race.step()
        rows = []
        for marble_id, result in sorted(race.results.items()):
            state = (
                "finished"
                if result.finish_order is not None
                else ("escaped" if race.marbles[marble_id].state == "escaped" else "stuck")
            )
            rows.append(
                {
                    "seed": seed,
                    "marble": marble_id,
                    "route": result.route,
                    "state": state,
                    "lost_at": list(result.lost_at) if result.lost_at else None,
                    "lost_how": result.lost_how,
                    "peak": race.peak.get(marble_id),
                    "last": race.last.get(marble_id),
                }
            )
        ride = {
            f"{name}[{index}]": [round(cell[0], 4), round(cell[1], 4), int(cell[2])]
            for (name, index), cell in sorted(race.ride.items())
        }
        return {"seed": seed, "racers": rows, "ride": ride}
    finally:
        race.close()


def _one(job):
    return trace_seed(*job)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=40)
    parser.add_argument("--first-seed", type=int, default=4001)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--runs", nargs="*", default=["orange_lead", "orange"])
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    jobs = [
        (seed, args.marbles, args.duration)
        for seed in range(args.first_seed, args.first_seed + args.seeds)
    ]
    if args.workers <= 1:
        seeds = [trace_seed(*job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            seeds = list(pool.map(_one, jobs))

    racers = [row for seed in seeds for row in seed["racers"]]
    outcome: Counter = Counter(f"{r['route']}/{r['state']}" for r in racers)
    sites: Counter = Counter(
        f"{r['lost_at'][0]}[{r['lost_at'][1]}]"
        for r in racers
        if r["state"] != "finished" and r["lost_at"]
    )
    how: Counter = Counter(
        r["lost_how"] for r in racers if r["state"] != "finished"
    )
    print(f"{len(racers)} racers over {args.seeds} seeds from {args.first_seed}")
    print(f"  by outcome {dict(outcome)}")
    print(f"  loss sites {dict(sites.most_common(14))}")
    print(f"  how        {dict(how)}")

    print("\n  losers, with the highest point each reached on a watched run:")
    for row in racers:
        if row["state"] == "finished":
            continue
        peak = row["peak"] or {}
        last = row["last"] or {}
        print(
            f"    seed {row['seed']} m{row['marble']} {row['route']}/{row['state']:8s} "
            f"lost {row['lost_at']} ({row['lost_how']})  peak "
            f"{peak.get('run')}[{peak.get('sample')}] rise {peak.get('rise')} "
            f"reach {peak.get('reach')} at {peak.get('speed')} wu/s  last "
            f"{last.get('run')}[{last.get('sample')}] rise {last.get('rise')}"
        )

    # The field's own envelope per sample, over every racer of every seed.
    ride: dict[str, list[float]] = {}
    for seed in seeds:
        for key, cell in seed["ride"].items():
            have = ride.get(key)
            if have is None:
                ride[key] = list(cell)
            else:
                have[0] = max(have[0], cell[0])
                have[1] = max(have[1], cell[1])
                have[2] += cell[2]
    for run in args.runs:
        rows = sorted(
            (int(key[len(run) + 1 : -1]), cell)
            for key, cell in ride.items()
            if key.startswith(f"{run}[")
        )
        if not rows:
            continue
        print(f"\n  {run}: the highest any marble rode, as a fraction of containment")
        print("    sample " + "".join(f"{index:>7}" for index, _ in rows[::4]))
        print("    rise   " + "".join(f"{cell[0]:>7.2f}" for _index, cell in rows[::4]))
        print("    reach  " + "".join(f"{cell[1]:>7.2f}" for _index, cell in rows[::4]))
        over = [(index, cell) for index, cell in rows if cell[0] >= 0.9]
        if over:
            print(
                f"    at or over 90% of containment at {len(over)} samples: "
                + ", ".join(f"{index}({cell[0]:.2f})" for index, cell in over[:24])
            )

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"seeds": seeds}, handle, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

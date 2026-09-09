"""What a racer that stops is doing in the seconds before it stops.

    python tools/sloped_stall_trace.py --seeds 96 --routes blue

Section 10 of the V1.10 brief. `leg2[99]` stalls 41 racers in 4,800 and the
600-race benchmark can only say that; the site's own geometry has no seam, no
step and no local minimum in the centreline's gradient, so whatever holds them
is about where in the channel they are rather than about where along it.

So this keeps a ring buffer per racer - the position in its own run's frame,
the speed, and what it is touching - and prints the buffer for every racer that
ends the race still in the machine. Every reading is in the located run's frame:
`across` as a fraction of the local half width, `rise` above the cradle's
lowest point in simulation units, and the bank, because on this course the
outside of a turn is the low side and a bank that unwinds lifts it.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG

from sloped.course import sloped_course
from sloped.race import SlopedRace

EVERY = 12          # ticks between samples; 20 a second
KEEP = 90           # samples kept per racer, so about four and a half seconds


class StallRace(SlopedRace):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tail: dict[int, deque] = {}

    def step(self) -> None:
        super().step()
        if self.ticks % EVERY:
            return
        for marble_id in list(self.world.marbles):
            place = self._where.get(marble_id)
            if place is None:
                continue
            name, index = place
            run = self.runs[name]
            position, _orientation, velocity, spin = self.marbles[marble_id].pose
            lateral, up, _forward = run.frames[index]
            centre = run.sim_path[index]
            offset = [position[axis] - centre[axis] for axis in range(3)]
            across = sum(offset[axis] * lateral[axis] for axis in range(3))
            height = sum(offset[axis] * up[axis] for axis in range(3))
            half = 0.5 * run.clear_width * run.widths[index]
            touching = sorted(
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
            )
            self.tail.setdefault(marble_id, deque(maxlen=KEEP)).append(
                {
                    "t": round(self.elapsed, 3),
                    "run": name,
                    "i": index,
                    "reach": round(across / max(half, 1e-9), 3),
                    "rise": round(height - run.floor_offset, 3),
                    "v": round(math.dist(velocity, (0.0, 0.0, 0.0)), 2),
                    "spin": round(math.dist(spin, (0.0, 0.0, 0.0)), 1),
                    "bank": round(math.degrees(run.banks[index]), 1),
                    "touch": touching,
                }
            )


def _one(job) -> list[dict[str, Any]]:
    seeds, routes, duration = job
    machine = sloped_course(routes=routes)
    out = []
    for seed in seeds:
        race = StallRace(machine, DEFAULT_CONFIG, seed, 8)
        limit = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
        try:
            while race.ticks < limit and not race.finished:
                race.step()
            for marble_id, result in race.results.items():
                if result.finish_order is not None:
                    continue
                if race.marbles[marble_id].state == "escaped":
                    continue
                out.append(
                    {
                        "seed": seed,
                        "marble": marble_id,
                        "slot": result.start_slot,
                        "route": result.route,
                        "last_touch": list(result.last_touch) if result.last_touch else None,
                        "tail": list(race.tail.get(marble_id, ())),
                    }
                )
        finally:
            race.close()
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=96)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--routes", default="blue", choices=("blue", "both"))
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--chunk", type=int, default=2)
    parser.add_argument("--show", type=int, default=6)
    parser.add_argument("--site", default="", help="only show stalls whose last touch starts with this")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    jobs = [
        (seeds[index : index + args.chunk], args.routes, args.duration)
        for index in range(0, len(seeds), args.chunk)
    ]
    if args.workers <= 1:
        batches = [_one(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            batches = list(pool.map(_one, jobs))
    stalls = [row for batch in batches for row in batch]

    sites = Counter(
        f"{row['last_touch'][0]}[{row['last_touch'][1]}]" if row["last_touch"] else "-"
        for row in stalls
    )
    print(f"{len(stalls)} racers still in the machine over {len(seeds)} seeds [{args.routes}]")
    print("  sites: " + ", ".join(f"{k} x{v}" for k, v in sites.most_common(12)))

    # Where they came to rest, and how they were sitting when they did.
    resting = [row["tail"][-1] for row in stalls if row["tail"]]
    if resting:
        print(
            "  at rest: mean reach "
            f"{sum(r['reach'] for r in resting) / len(resting):+.3f}, "
            f"mean rise {sum(r['rise'] for r in resting) / len(resting):+.3f}, "
            f"mean speed {sum(r['v'] for r in resting) / len(resting):.2f}"
        )
        print("  touching at rest: " + ", ".join(
            f"{k} x{v}" for k, v in Counter(
                ",".join(r["touch"]) or "-" for r in resting
            ).most_common(8)
        ))

    shown = 0
    for row in stalls:
        site = f"{row['last_touch'][0]}[{row['last_touch'][1]}]" if row["last_touch"] else "-"
        if args.site and not site.startswith(args.site):
            continue
        if shown >= args.show:
            break
        shown += 1
        print()
        print(f"  seed {row['seed']} marble {row['marble']} slot {row['slot']} at {site}")
        for frame in row["tail"][-24:]:
            print(
                f"    t={frame['t']:>7} {frame['run']:<12}[{frame['i']:>3}] "
                f"reach {frame['reach']:>+6.3f} rise {frame['rise']:>+6.3f} "
                f"v {frame['v']:>6.2f} spin {frame['spin']:>6.1f} bank {frame['bank']:>+6.1f} "
                f"{','.join(frame['touch']) or '-'}"
            )

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"routes": args.routes, "stalls": stalls}, handle, indent=1)
            handle.write("\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Launch marbles onto the merge shoulder and see which ones get out.

Section 5 of the V1.15 brief: a harness that reproduces the `final[10]` failure
without running whole races, so a geometry candidate can be judged in seconds
rather than in an hour of benchmark.

A marble is placed in the **sprint's own gravity-aligned frame** - the frame
`tools/sloped_final_trace.py` reports in - at an `along`, an `across` and a
clearance above whatever the station's floor is there, with a velocity given as
(down the sprint, east, vertical). It is then run until it either passes
`CLEARED` or stops moving for `STOPPED_TICKS`.

    python tools/sloped_final_lab.py --grid
    python tools/sloped_final_lab.py --grid --knobs '{"taper_to": 1.673}'

`--knobs` names are `sloped.stations.MergeCatch`'s own attributes in layout
units plus `guard_window`, which is `sloped.course.MERGE_GUARD_WINDOW`, so a
candidate that looks good here is handed to the whole-race benchmark unchanged.

## The verdict is the marble's own position, not a containment test

`sloped.race`'s `lost_at` is a *containment* verdict and on the apron it fires
for marbles that are doing exactly what the station is for - `MergeCatch.holds`
exists because of it. So this tool asks only two things of a marble: did its
`along` pass the front of the window, and did it stop. Both are unambiguous.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG
from marble3d.units import MARBLE_RADIUS
from marble3d.world import MarbleWorld

from sloped.course import sloped_course
from tools.sloped_final_shoulder import datum, frame

# How far down the sprint counts as out of the junction. `final[20]` is six
# samples past the apron's front edge and past the guard window's close.
CLEARED = 20.0 * 0.3259
STOPPED_SPEED = 1.2
STOPPED_TICKS = 180
REACH = 40.0


def _apply(knobs: dict[str, Any]) -> None:
    """Every merge constant this lab can move, set before the machine is built.

    Layout units throughout, because that is what `MergeCatch` stores, and the
    one exception is `guard_window`, which is a sample tuple.
    """
    import sloped.course as course
    from sloped.stations import MergeCatch

    for name in ("BACK", "FRONT", "TAPER_FROM", "TAPER_TO", "ACROSS", "ROOF", "FUNNEL",
                 "WALL_AT", "RIM_MIN", "LIP_OPEN"):
        key = name.lower()
        if key in knobs and knobs[key] is not None:
            setattr(MergeCatch, name, knobs[key])
    if knobs.get("guard_window") is not None:
        course.MERGE_GUARD_WINDOW = tuple(knobs["guard_window"])


# Anything this far under the local cradle bottom is below the station, not a
# floor of it.
UNDER = -0.8


def floor_under(world, point, base: float) -> tuple[float | None, str | None]:
    """The surface a marble would stand on under a point, as (height, owner).

    A **layer walk**, not one ray, and that is a correction of this tool's own
    first version. The apron has a roof over the whole of it, so a single
    downward ray is answered by the roof and a marble placed a radius under
    that answer is placed *on top of the station*. The first sweep this tool
    ran therefore reported 94 of 105 launches clearing, with the marbles
    rolling along the roof and off its front edge.

    So every surface under the point is collected, and the floor is the lowest
    one still within `UNDER` of the sprint's own cradle bottom at that station.
    """
    out = []
    y = point[1]
    floor_y = base + UNDER - 2.0
    for _ in range(8):
        if y <= floor_y:
            break
        hits = world.ray_batch([(point[0], y, point[2])], [(point[0], floor_y, point[2])])
        body, _fraction, hit = hits[0]
        if body < 0:
            break
        out.append((hit[1], world.owner_of(body)))
        y = hit[1] - 0.01
    standing = [row for row in out if row[0] - base > UNDER]
    if not standing:
        return None, None
    return standing[-1]


class Bench:
    """One built course, reused for every launch in a job."""

    def __init__(self, knobs: dict[str, Any] | None = None) -> None:
        _apply(knobs or {})
        self.machine = sloped_course(routes="both")
        self.world = MarbleWorld(DEFAULT_CONFIG)
        self.machine.build(self.world)
        self.final = self.machine.runs["final"]           # type: ignore[attr-defined]
        self.origin, self.forward, self.side = frame(self.final)
        self.spacing = math.dist(self.final.sim_path[0], self.final.sim_path[1])
        self.hz = DEFAULT_CONFIG.physics.physics_hz

    def close(self) -> None:
        self.world.close()

    def world_point(self, along: float, across: float, height: float):
        base = datum(self.final, along)
        return tuple(
            self.origin[axis]
            + self.forward[axis] * along
            + self.side[axis] * across
            + (0.0, base - self.origin[1] + height, 0.0)[axis]
            for axis in range(3)
        )

    def local(self, point) -> tuple[float, float, float]:
        offset = [point[axis] - self.origin[axis] for axis in range(3)]
        along = sum(offset[axis] * self.forward[axis] for axis in range(3))
        across = sum(offset[axis] * self.side[axis] for axis in range(3))
        return along, across, point[1] - datum(self.final, along)

    def world_vector(self, forward: float, across: float, vertical: float):
        return tuple(
            self.forward[axis] * forward + self.side[axis] * across + (0.0, vertical, 0.0)[axis]
            for axis in range(3)
        )

    def launch(
        self,
        along: float,
        across: float,
        velocity: tuple[float, float, float],
        clearance: float = MARBLE_RADIUS + 0.02,
        duration: float = 6.0,
    ) -> dict[str, Any]:
        """One marble, placed a clearance above the floor under it."""
        probe = self.world_point(along, across, 4.0)
        height, owner = floor_under(self.world, probe, datum(self.final, along))
        if height is None:
            return {"along": along, "across": across, "verdict": "no_floor"}
        start = (probe[0], height + clearance, probe[2])
        self.world.add_marble(0, start, self.world_vector(*velocity))
        ticks = int(round(duration * self.hz))
        still = 0
        best = -99.0
        try:
            for _ in range(ticks):
                self.world.step()
                position, _orientation, speed_vector, _spin = self.world.marble_state(0)
                current, lateral, rise = self.local(position)
                best = max(best, current)
                if current >= CLEARED:
                    return {
                        "along": along,
                        "across": across,
                        "verdict": "cleared",
                        "at": round(current, 3),
                        "rest_across": round(lateral, 3),
                    }
                speed = math.dist(speed_vector, (0.0, 0.0, 0.0))
                still = still + 1 if speed < STOPPED_SPEED else 0
                if still >= STOPPED_TICKS:
                    return {
                        "along": along,
                        "across": across,
                        "verdict": "stuck",
                        "at": round(current, 3),
                        "sample": round(current / self.spacing, 2),
                        "rest_across": round(lateral, 3),
                        "rise": round(rise, 3),
                        "floor": owner,
                    }
                if rise < -4.0:
                    return {"along": along, "across": across, "verdict": "fell", "at": round(current, 3)}
            position, _orientation, _velocity, _spin = self.world.marble_state(0)
            current, lateral, rise = self.local(position)
            return {
                "along": along,
                "across": across,
                "verdict": "slow",
                "at": round(current, 3),
                "sample": round(current / self.spacing, 2),
                "rest_across": round(lateral, 3),
                "furthest": round(best, 3),
            }
        finally:
            self.world.remove_marble(0)


def grid_job(knobs: dict[str, Any], cases: Sequence[tuple[float, float, tuple[float, float, float]]]):
    bench = Bench(knobs)
    try:
        return [
            dict(
                bench.launch(along, across, velocity),
                speed=round(velocity[0], 1),
                lateral=round(abs(velocity[1]) / max(velocity[0], 1e-6), 2),
            )
            for along, across, velocity in cases
        ]
    finally:
        bench.close()


def default_cases(
    alongs: Sequence[float],
    acrosses: Sequence[float],
    speeds: Sequence[float],
    lateral: Sequence[float] = (0.0,),
):
    """The corridor the trace measured, as (along, across, velocity) rows.

    `lateral` is the sideways component as a fraction of the forward one, and
    the sign is always **toward** the channel, because that is the direction a
    marble coming off the apron's far wall carries. Zero is the case that
    matters most: a marble that is simply running down the shoulder.
    """
    return [
        (along, across, (speed, fraction * speed * (1.0 if across < 0 else -1.0), 0.0))
        for along in alongs
        for across in acrosses
        for speed in speeds
        for fraction in lateral
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--knobs", default="", help="JSON object of merge knobs")
    parser.add_argument("--alongs", type=float, nargs="*", default=[-1.0, 0.0, 1.0, 2.0])
    parser.add_argument(
        "--acrosses", type=float, nargs="*",
        default=[-3.4, -3.0, -2.6, -2.2, -1.9],
    )
    parser.add_argument("--speeds", type=float, nargs="*", default=[6.0, 12.0, 20.0, 30.0])
    parser.add_argument(
        "--lateral", type=float, nargs="*", default=[0.0, 0.2],
        help="sideways launch speed as a fraction of forward, toward the channel",
    )
    parser.add_argument("--duration", type=float, default=6.0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    knobs = json.loads(args.knobs) if args.knobs else {}
    cases = default_cases(args.alongs, args.acrosses, args.speeds, args.lateral)
    chunks = [cases[index::args.workers] for index in range(args.workers)]
    chunks = [chunk for chunk in chunks if chunk]
    if len(chunks) <= 1:
        rows = grid_job(knobs, cases)
    else:
        with ProcessPoolExecutor(max_workers=len(chunks)) as pool:
            rows = [row for part in pool.map(_one, [(knobs, chunk) for chunk in chunks]) for row in part]

    verdicts: Counter = Counter(row["verdict"] for row in rows)
    cleared = verdicts["cleared"]
    print(f"knobs {knobs}")
    print(f"{len(rows)} launches:  " + "  ".join(f"{k} {v}" for k, v in verdicts.most_common()))
    print(f"cleared {cleared}/{len(rows)} = {cleared / max(len(rows), 1):.3f}")
    stuck = [row for row in rows if row["verdict"] in ("stuck", "slow")]
    if stuck:
        where: Counter = Counter(f"f[{int(round(row.get('sample', 0)))}]" for row in stuck)
        print(f"  stopped at  {dict(where.most_common(10))}")
        print("  worst rows:")
        for row in sorted(stuck, key=lambda r: r.get("at", 0))[:10]:
            print(
                f"    launch along {row['along']:+6.2f} across {row['across']:+6.2f} "
                f"speed {row['speed']:>5} -> {row['verdict']} at f[{row.get('sample')}] "
                f"across {row.get('rest_across')} rise {row.get('rise')} floor {row.get('floor')}"
            )
    by_across: dict[float, Counter] = {}
    for row in rows:
        by_across.setdefault(row["across"], Counter())[row["verdict"]] += 1
    print("\n  by launch across:")
    for across in sorted(by_across):
        counts = by_across[across]
        total = sum(counts.values())
        print(f"    {across:+6.2f}  cleared {counts['cleared']:>3}/{total:<3}  " + "  ".join(
            f"{k} {v}" for k, v in counts.most_common() if k != "cleared"
        ))

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"knobs": knobs, "rows": rows}, handle, indent=1)
        print(f"\nwrote {args.out}")
    return 0


def _one(job):
    return grid_job(*job)


if __name__ == "__main__":
    raise SystemExit(main())

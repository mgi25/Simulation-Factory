"""Measure the *production* neon bowl with the lab's own orbit metric.

Section 2 of the experiment plan makes a falsifiable prediction. It argues
that the current architecture cannot produce bowl motion, because gravity in
the simulation plane is a constant vector rather than the tangential
projection of one - so the disc has a restoring force on the semicircle where
`sim_y < BOWL_CENTRE_Y` and an expelling force on the other. If that is right,
a racer crossing the neon bowl should accumulate very little angular travel
about the bowl axis before it reaches the drain.

This measures it, with the same accumulated-angle metric the two prototypes
are scored on, over the real neon replay. It reads the replay only - no
production module is imported and nothing is re-simulated - so it can be run
against any recorded race and it cannot perturb one.

The bowl's centre and radius come out of the replay's own course metadata,
which `race/courses/neon.py` exports precisely so the renderer does not have
to guess where the disc is. The same export is what makes this measurable
from outside.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def wrap(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def measure(replay: dict) -> dict:
    course = replay.get("course", {})
    metadata = course.get("metadata", course)
    centre_x = float(metadata["bowl_centre_x"])
    centre_y = float(metadata["bowl_centre_y"])
    radius = float(metadata["bowl_radius"])

    travel: dict[int, float] = {}
    last: dict[int, float] = {}
    inside_frames: dict[int, int] = {}
    peak_rho: dict[int, float] = {}
    fps = float(replay.get("fps", 60))

    for frame in replay["frames"]:
        for racer in frame["racers"]:
            racer_id = int(racer["id"])
            dx = float(racer["x"]) - centre_x
            dy = float(racer["y"]) - centre_y
            rho = math.hypot(dx, dy) / radius
            if rho > 1.0:
                # Outside the disc. Drop the angle memory so a racer that
                # leaves and returns does not book the angle it swept while
                # it was somewhere else entirely.
                last.pop(racer_id, None)
                continue
            angle = math.atan2(dy, dx)
            if racer_id in last:
                travel[racer_id] = travel.get(racer_id, 0.0) + wrap(angle - last[racer_id])
            last[racer_id] = angle
            inside_frames[racer_id] = inside_frames.get(racer_id, 0) + 1
            peak_rho[racer_id] = max(peak_rho.get(racer_id, 0.0), rho)

    revolutions = {
        racer_id: abs(value) / (2.0 * math.pi) for racer_id, value in travel.items()
    }
    values = sorted(revolutions.values())
    if not values:
        raise SystemExit("no racer entered the bowl disc; is this a neon replay?")
    middle = len(values) // 2
    return {
        "racers_through_the_bowl": len(values),
        "median_revolutions": values[middle]
        if len(values) % 2
        else 0.5 * (values[middle - 1] + values[middle]),
        "mean_revolutions": sum(values) / len(values),
        "min_revolutions": values[0],
        "max_revolutions": values[-1],
        "fraction_over_one_revolution": sum(1 for v in values if v >= 1.0) / len(values),
        "fraction_over_half_a_revolution": sum(1 for v in values if v >= 0.5) / len(values),
        "mean_seconds_in_the_bowl": sum(inside_frames.values()) / len(inside_frames) / fps,
        "per_racer_revolutions": {str(k): round(v, 4) for k, v in sorted(revolutions.items())},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("replay", nargs="?", default=os.path.join("output", "neon_v11", "neon_7.json"))
    parser.add_argument("--output", default=os.path.join("output", "physics_lab", "production_bowl.json"))
    args = parser.parse_args(argv)

    if not os.path.isfile(args.replay):
        raise SystemExit(
            f"no replay at {args.replay}; run tools/neon_proof.py --replay --seed 7 first"
        )
    with open(args.replay, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    if replay.get("mode") != "race":
        raise SystemExit(f"{args.replay} is not a race replay")

    report = measure(replay)
    report["replay"] = os.path.basename(args.replay)
    report["seed"] = replay.get("seed")
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(json.dumps(report, indent=2))
    print(f"-> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

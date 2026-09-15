"""Compare the three Race #2 concepts on the things that decide between them.

Usage:

    python tools/race2_concepts.py --seeds=24 --out=docs/validation/race2

Every concept is built on the same skeleton - the same plan, drop, start and
run-out - so the comparison is about competitive topology and nothing else. Six
criteria, in the order the brief names them:

    event density          events per second, by `race2.events`' definition
    continuity             the longest span with no event in it
    fairness               start-slot to finish-rank correlation, and the
                           winner distribution across the eight bays
    health                 finish rate, all-eight rate, stuck and escape rates
    volatility             lead changes and overtakes per race
    camera potential       pack spread, and how much of the course is visible
                           from one position - reported as geometry rather than
                           scored, because a camera has not been built yet

The one criterion not scored is prettiness. A concept is chosen here on whether
the race is worth watching, and the film is built afterwards.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race2 import concepts
from race2.bench import run_seeds


def geometry(name: str) -> dict:
    """What the built course is, before anything is raced on it."""
    course = concepts.build(name)
    footprint = course.footprint()
    wheels = []
    for module in course.machine:
        if type(module).__name__ == "Wheel":
            wheels.append(
                {
                    "id": module.id,
                    "half_width": round(module.half_width(), 3),
                    "side_gap": round(module.side_gap(), 3),
                    "blades": module.blades,
                    "rate": round(module.rate, 3),
                    "gate": module.side_gap() < 2.0 * 0.285,
                }
            )
    widths = []
    for stage in course.stages:
        run = course.runs[stage.runs[0]]
        mid = len(run.widths) // 2
        widths.append(
            (stage.name, round(2.0 * 0.94 * run.scale * run.widths[mid], 2))
        )
    return {
        "title": course.title,
        "runs": len(course.runs),
        "stages": len(course.stages),
        "splits": len(course.splits()),
        "layout_length": round(course.layout_length(), 2),
        "drop": round(course.drop(), 2),
        "footprint": [round(v, 2) for v in footprint],
        "plan_area": round(footprint[0] * footprint[1], 1),
        "mean_slope_deg": round(
            math.degrees(math.asin(min(1.0, course.drop() / course.layout_length()))), 2
        ),
        "clear_width_by_stage": widths,
        "wheels": wheels,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=24)
    parser.add_argument("--first", type=int, default=1)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    names = [n for n in concepts.concept_names()
             if not args.only or n in args.only.split(",")]
    seeds = list(range(args.first, args.first + args.seeds))
    report: dict = {"seeds": len(seeds), "first_seed": args.first, "concepts": {}}

    for name in names:
        facts = geometry(name)
        print(f"\n=== {facts['title']} ===")
        print(f"  {facts['runs']} runs, {facts['splits']} split(s), "
              f"{facts['layout_length']} units, {facts['drop']} drop, "
              f"plan {facts['footprint'][0]} x {facts['footprint'][1]} "
              f"({facts['plan_area']} sq), mean slope {facts['mean_slope_deg']} deg")
        print("  clear width: " + ", ".join(f"{k} {v}" for k, v in facts["clear_width_by_stage"]))
        for wheel in facts["wheels"]:
            print(f"  wheel {wheel['id']:<9} gap {wheel['side_gap']:5.2f} "
                  f"{'GATE' if wheel['gate'] else 'pass'} "
                  f"{wheel['blades']} blades at {wheel['rate']}")

        bench = run_seeds(name, seeds, duration=args.duration,
                          workers=args.workers or None)
        print(bench.summary())
        report["concepts"][name] = {"geometry": facts, "benchmark": bench.to_json()}

    # The comparison table, which is the actual deliverable.
    print("\n" + "=" * 78)
    header = (f"{'concept':<11}{'finish':>8}{'all-8':>7}{'stuck':>7}{'slot r':>8}"
              f"{'lead':>6}{'ev/s':>6}{'gap':>6}{'worst':>7}{'race s':>8}{'podium':>8}")
    print(header)
    print("-" * 78)
    for name in names:
        data = report["concepts"][name]["benchmark"]
        print(f"{name:<11}{data['finish_rate'] * 100:7.1f}%{data['all_finished_rate'] * 100:6.0f}%"
              f"{data['stuck_rate'] * 100:6.1f}%{data['slot_correlation']:+8.3f}"
              f"{data['mean_lead_changes']:6.1f}{data['mean_density']:6.2f}"
              f"{data['mean_longest_gap']:6.2f}{data['worst_longest_gap']:7.2f}"
              f"{data['mean_last_finish']:8.1f}{data['mean_podium_gap']:8.3f}")

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, "concepts.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)
        print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

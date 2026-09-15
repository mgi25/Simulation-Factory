"""Scan the channel's wall height against what it costs and what it buys.

The wall is the one number where the physics and the picture pull against each
other, and the pull is not small:

    a tall wall contains a marble thrown up the outside of a banked hairpin
    a tall wall hides that marble from any camera below the map view

`race2.track` explains why the wall cannot simply be the profile scale's own
(1.60 layout units at scale 2.0, which needs 50 degrees of look-down over a
corridor). This finds the lowest cap that still contains the field.

    python tools/race2_wall.py --caps=0.62,0.85,1.00,1.20 --seeds=40
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--caps", default="0.62,0.85,1.00,1.20")
    parser.add_argument("--seeds", type=int, default=40)
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = []
    print(f"{'cap':>6}{'finish':>9}{'all-8':>8}{'escape':>8}{'stuck':>7}"
          f"{'look-down':>11}{'lead':>7}{'ev/s':>7}")
    print("-" * 61)
    for raw in args.caps.split(","):
        cap = float(raw)
        # Set before the import so every worker process inherits it: the pool
        # re-imports `race2.track` in each child, and a value set after the
        # parent imported it would reach the parent only.
        os.environ["RACE2_WALL_CAP"] = f"{cap}"
        from race2.bench import run_seeds

        bench = run_seeds(args.course, list(range(1, args.seeds + 1)))
        from importlib import reload

        import race2.courses
        import race2.track

        reload(race2.track)
        reload(race2.courses)
        course = race2.courses.build(args.course)
        worst = max(run.wall_angle() for run in course.runs.values())
        data = bench.to_json()
        rows.append({"cap": cap, "worst_look_down": round(worst, 2), **data})
        print(f"{cap:6.2f}{data['finish_rate'] * 100:8.1f}%"
              f"{data['all_finished_rate'] * 100:7.0f}%"
              f"{data['escape_rate'] * 100:7.1f}%{data['stuck_rate'] * 100:6.1f}%"
              f"{worst:10.1f}d{data['mean_lead_changes']:7.1f}"
              f"{data['mean_density']:7.2f}")

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

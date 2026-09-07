"""Split one benchmark run into the four validation files section 29 asks for.

    python tools/sloped_v11_validation.py --bench bench600.json

Writes, under `docs/validation/sloped_race_v1/`:

    fairness_v11.json      slot win rates, checkpoint ranks, strongest/weakest
    reliability_v11.json   finish, all-eight, escape, stopped, loss locations
    routes_v11.json        usage, travel time, failure and win rate per route
    determinism_v11.json   written by `tools/sloped_determinism.py`, not here

Each file carries the V1 baseline beside the V1.1 number, labelled, because
section 18 is explicit that the old benchmark was taken on a physically
defective course and must not be quoted as a comparison without saying so.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT_DIR = Path("docs") / "validation" / "sloped_race_v1"

# `docs/sloped_race_v1.md`, from a course whose fork was unreachable, whose
# merge apron trapped marbles on the sprint's guard rails and whose stud row
# stood at the leg1 seam. Kept beside every V1.1 number and never quoted
# without this note.
V1_BASELINE = {
    "source": "docs/sloped_race_v1.md, 600 seeds / 4800 racers",
    "warning": (
        "taken on a physically defective course: the orange route was "
        "unreachable, the merge apron trapped marbles on the sprint's guard "
        "rails (319 of 747 losses) and the stud row stood where the field "
        "arrives at 50 wu/s (193 more). Not a like-for-like comparison."
    ),
    "finish_rate": 0.8435,
    "escape_rate": 0.0833,
    "stuck_rate": 0.0731,
    "all_finished_races": 161,
    "all_finished_rate": 161 / 600,
    "slot_win_ratio": 8.87,
    "strongest_slot": 2,
    "strongest_win_rate": 0.2217,
    "weakest_slot": 0,
    "weakest_win_rate": 0.0250,
    "early_rank_span_places": 3.61,
    "loss_sites": {"blue[100]": 319, "leg1[0]": 193, "launch[100]": 44, "leg1[80]": 39},
    "routes": {"blue": 1.0, "orange": 0.0},
}


def _ratio(slots: dict[str, Any]) -> dict[str, Any]:
    """Strongest-to-weakest win rate, and what to say when the weakest is zero.

    V1 reported this as 8.87. A ratio is undefined when a slot never wins, and
    reporting `None` there hides the fact that the spread is *worse* than any
    finite ratio - so the zero case is named and the difference in percentage
    points is given instead.
    """
    rates = {int(k): float(v["win_rate"]) for k, v in slots.items()}
    strongest = max(rates, key=lambda s: rates[s])
    weakest = min(rates, key=lambda s: rates[s])
    high, low = rates[strongest], rates[weakest]
    return {
        "per_slot": rates,
        "expected": round(1.0 / len(rates), 6),
        "strongest_slot": strongest,
        "strongest_win_rate": round(high, 6),
        "weakest_slot": weakest,
        "weakest_win_rate": round(low, 6),
        "ratio": round(high / low, 4) if low > 0 else None,
        "ratio_note": None if low > 0 else f"slot {weakest} never won; the ratio is unbounded",
        "spread_points": round(100.0 * (high - low), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, help="the benchmark JSON")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--start-lab", default="", help="a startlab scan JSON, optional")
    args = parser.parse_args(argv)

    with open(args.bench, "r", encoding="utf-8") as handle:
        bench = json.load(handle)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    races = int(bench["races"])
    fairness = {
        "races": races,
        "racers": int(bench["racers"]),
        "routes_built": bench.get("routes_built", "blue"),
        "checkpoints": bench["checkpoints"],
        "win_rate": _ratio(bench["fairness"]["slots"]),
        "slots": bench["fairness"]["slots"],
        "spearman": bench["fairness"].get("spearman"),
        "v1_baseline": {
            key: V1_BASELINE[key]
            for key in (
                "source",
                "warning",
                "slot_win_ratio",
                "strongest_slot",
                "strongest_win_rate",
                "weakest_slot",
                "weakest_win_rate",
                "early_rank_span_places",
            )
        },
    }
    if args.start_lab:
        with open(args.start_lab, "r", encoding="utf-8") as handle:
            fairness["start_lab"] = json.load(handle)

    reliability = {
        "races": races,
        "racers": int(bench["racers"]),
        **bench["reliability"],
        "v1_baseline": {
            key: V1_BASELINE[key]
            for key in (
                "source",
                "warning",
                "finish_rate",
                "escape_rate",
                "stuck_rate",
                "all_finished_races",
                "all_finished_rate",
                "loss_sites",
            )
        },
    }

    routes = {
        "races": races,
        "routes_built": bench.get("routes_built", "blue"),
        "per_route": bench["routes"],
        "v1_baseline": {
            "source": V1_BASELINE["source"],
            "warning": V1_BASELINE["warning"],
            "usage": V1_BASELINE["routes"],
            "note": "orange was unreachable to a completed finish in V1",
        },
    }

    written = []
    for name, payload in (
        ("fairness_v11.json", fairness),
        ("reliability_v11.json", reliability),
        ("routes_v11.json", routes),
    ):
        path = out_dir / name
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=1, sort_keys=True)
            handle.write("\n")
        written.append(str(path))
        print(f"wrote {path}")

    quality = bench["quality"]
    print()
    print(f"finish {reliability['finish_rate']:.4f}  escape {reliability['escape_rate']:.4f}  "
          f"stuck {reliability['stuck_rate']:.4f}  all-eight {reliability['all_finished_rate']:.4f}")
    block = fairness["win_rate"]
    print(f"win ratio {block['ratio']}  strongest {block['strongest_slot']} "
          f"({block['strongest_win_rate']:.4f})  weakest {block['weakest_slot']} "
          f"({block['weakest_win_rate']:.4f})  spread {block['spread_points']:.2f} points")
    print(f"lead changes {quality['mean_lead_changes']:.2f}  "
          f"winner lock {quality['mean_winner_lock_fraction']:.3f}  "
          f"final margin {quality['median_final_margin']:.3f} s  "
          f"winner worst rank {quality['mean_winner_worst_rank']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

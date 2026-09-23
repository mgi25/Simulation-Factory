"""Small, controlled configuration sweep for MULTIPLYING SHELL Phase 3B.

This is deliberately a named matrix rather than a combinatorial search.  Each
row changes one understandable part of the arena and all rows use the same
seed interval, so a difference can be attributed to geometry, toughness, or
rotation instead of to sampling noise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from satisfying.multishell import DEFAULT_CONFIG, MultishellConfig, difficulty_profile
from satisfying.multishell_cli import _rehydrate, run_batch
from satisfying.multishell_evaluator import summarise


GEOMETRY = {
    "panel_counts": (12, 18, 22, 30, 36),
    "openings_per_shell": (3, 3, 2, 2, 2),
    "opening_slots": (2, 2, 2, 2, 1),
}

TIGHTER_GEOMETRY = {
    "panel_counts": (12, 20, 24, 32, 40),
    "openings_per_shell": (3, 3, 2, 2, 2),
    "opening_slots": (2, 2, 2, 2, 1),
}

AGGRESSIVE_GEOMETRY = {
    "panel_counts": (12, 22, 26, 36, 44),
    "openings_per_shell": (3, 3, 2, 2, 2),
    "opening_slots": (2, 2, 2, 2, 1),
}

FINALIST_GEOMETRY = {
    "panel_counts": (12, 24, 28, 38, 46),
    "openings_per_shell": (3, 3, 2, 2, 2),
    "opening_slots": (2, 2, 2, 2, 1),
}


def configurations() -> dict[str, MultishellConfig]:
    geometry = DEFAULT_CONFIG.replace(**GEOMETRY)
    moderate = geometry.replace(break_thresholds=(1.8, 3.0, 4.8, 7.0, 9.5))
    strong = geometry.replace(break_thresholds=(1.8, 3.2, 5.0, 7.5, 11.0))
    tighter = DEFAULT_CONFIG.replace(**TIGHTER_GEOMETRY)
    tighter_moderate = tighter.replace(break_thresholds=(1.8, 3.0, 4.8, 7.0, 9.5))
    tighter_strong = tighter.replace(break_thresholds=(1.8, 3.2, 5.0, 7.5, 11.0))
    aggressive = DEFAULT_CONFIG.replace(**AGGRESSIVE_GEOMETRY)
    aggressive_cooperative = aggressive.replace(
        break_thresholds=(1.8, 2.8, 4.4, 6.6, 9.0), omega_falloff=0.82
    )
    aggressive_tough = aggressive.replace(
        break_thresholds=(1.8, 3.0, 4.8, 7.0, 9.5), omega_falloff=0.82
    )
    finalist = DEFAULT_CONFIG.replace(**FINALIST_GEOMETRY)
    finalist_cooperative = finalist.replace(
        break_thresholds=(1.8, 2.8, 4.4, 6.6, 9.0), omega_falloff=0.82
    )
    finalist_tough = finalist.replace(
        break_thresholds=(1.8, 3.0, 4.8, 7.0, 9.5), omega_falloff=0.82
    )
    return {
        "baseline": DEFAULT_CONFIG,
        "geometry": geometry,
        "geometry_toughness_moderate": moderate,
        "geometry_toughness_strong": strong,
        "geometry_toughness_moderate_rotation_090": moderate.replace(omega_falloff=0.90),
        "geometry_toughness_moderate_rotation_082": moderate.replace(omega_falloff=0.82),
        "geometry_toughness_moderate_rotation_074": moderate.replace(omega_falloff=0.74),
        "tighter_geometry_toughness_moderate_rotation_090": tighter_moderate.replace(omega_falloff=0.90),
        "tighter_geometry_toughness_moderate_rotation_082": tighter_moderate.replace(omega_falloff=0.82),
        "tighter_geometry_toughness_strong_rotation_082": tighter_strong.replace(omega_falloff=0.82),
        "aggressive_geometry_cooperative_rotation_082": aggressive_cooperative,
        "aggressive_geometry_tough_rotation_082": aggressive_tough,
        "finalist_geometry_cooperative_rotation_082": finalist_cooperative,
        "finalist_geometry_tough_rotation_082": finalist_tough,
    }


def headline(summary: dict) -> dict:
    return {
        "escape_rate": summary["escape_rate"],
        "timeout_rate": summary["failure_reasons"].get("timeout", 0) / summary["count"],
        "pass_rate_by_shell": summary["pass_rate_by_shell"],
        "duration": summary["duration"],
        "population": summary["population_total"],
        "first_spawn": summary["first_spawn"],
        "collisions_per_second": summary["collision_rate"],
        "meaningful_escalation": summary["escalation_meaningful"],
        "breaks": summary["breaks"],
        "shared_breaks": summary["shared_breaks"],
        "population_cap_hits": summary["flags"]["population_capped"],
        "solver_faults": summary["flags"]["instrument_fault"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--only", action="append", default=[])
    args = parser.parse_args()

    rows = []
    seeds = range(args.start, args.start + args.count)
    selected = configurations()
    if args.only:
        selected = {name: selected[name] for name in args.only}
    for name, config in selected.items():
        records = run_batch(seeds, config, workers=args.workers)
        summary = summarise(_rehydrate(records))
        rows.append(
            {
                "name": name,
                "config": config.as_dict(),
                "difficulty_profile": difficulty_profile(config),
                "headline": headline(summary),
            }
        )
        print(json.dumps({"name": name, **headline(summary)}, sort_keys=True))

    payload = {"seed_start": args.start, "seed_count": args.count, "rows": rows}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

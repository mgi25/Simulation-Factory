"""Deep-screen the Phase 3B shortlist for visual, damage, and audio risks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from satisfying.multishell import simulate
from satisfying.multishell_evaluator import evaluate
from satisfying.multishell_playback import document_for
from satisfying.multishell_score import schedule
from satisfying.multishell_visual import (
    centre_alignment_report,
    readability_report,
    safe_area_report,
)


ACCEPTED_SEEDS = (
    17275, 15793, 9324, 13361, 14705, 17283, 8292,
    16629, 17251, 16733, 3499, 14773, 12197,
)
REVIEW_SEEDS = (15793, 8292, 17251, 16733, 12197, 14705)


def screen(seed: int, record: dict) -> dict:
    run = simulate(seed)
    evaluation = evaluate(run)
    document = document_for(seed)
    readability = readability_report(document, fps=60.0)
    alignment = centre_alignment_report(document, fps=60.0)
    safe_area = safe_area_report(document)
    score = schedule(document)
    audio = score.metrics
    audio_thirds = audio["progression"]["thirds"]
    meaningful = record["meaningful_thirds"]
    collisions = record["collision_thirds"]
    population = record["thirds_population"]
    return {
        "seed": seed,
        "duration": record["duration"],
        "first_spawn": record["first_spawn"],
        "population": record["population_total"],
        "population_thirds": population,
        "collision_thirds": collisions,
        "meaningful_thirds": meaningful,
        "strict_escalation": {
            "population": population[2] > population[1] > population[0],
            "collisions": collisions[2] > collisions[1] > collisions[0],
            "meaningful": meaningful[2] > meaningful[1] > meaningful[0],
        },
        "escape_route": record["escape_route"],
        "escape_generation": record["escape_generation"],
        "breaks": record["breaks"],
        "shared_breaks": record["shared_breaks"],
        "cooperative_outer_breaks": record["cooperative_outer_breaks"],
        "cooperative_break_details": [
            detail
            for detail in evaluation.metrics["damage"]["break_details"]
            if detail["unique_contributing_balls"] > 1
        ],
        "outer_dwell_ball_seconds": record["dwell"][-2],
        "readability": readability,
        "pile_warning": readability["longest_triple_merge_seconds"] > 0.75,
        "alignment": alignment,
        "safe_area": safe_area,
        "audio": {
            "events_per_second": audio["event_density_hz"],
            "collisions_per_second": audio["collision_density_hz"],
            "max_polyphony": audio["max_scheduled_polyphony"],
            "median_polyphony": audio["median_scheduled_polyphony"],
            "simultaneous_onsets": audio["simultaneous_within_cluster"],
            "harsh_pairs": audio["consonance"]["harsh_pairs"],
            "thirds": audio_thirds,
            "density_warning": max(row["events_per_second"] for row in audio_thirds) > 12.0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortlist", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--population", type=Path)
    parser.add_argument("--validation-dir", type=Path)
    args = parser.parse_args()
    source = json.loads(args.shortlist.read_text(encoding="utf-8"))
    rows = [screen(int(row["seed"]), row) for row in source["candidates"]]
    rejected = {
        15009: "1.167 s severe triple-ball merge and non-monotonic meaningful thirds",
        19945: "1.300 s severe triple-ball merge",
        17970: "2.800 s severe triple-ball merge",
    }
    for row in rows:
        row["decision"] = "accepted" if row["seed"] in ACCEPTED_SEEDS else "rejected"
        row["decision_reason"] = rejected.get(row["seed"], "passes engineering screen")
    payload = {
        "config_digest": source["config_digest"],
        "source_seed_count": 20000,
        "accepted_seeds": list(ACCEPTED_SEEDS),
        "review_seeds": list(REVIEW_SEEDS),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.validation_dir:
        args.validation_dir.mkdir(parents=True, exist_ok=True)
        accepted = [
            row for row in source["candidates"] if int(row["seed"]) in ACCEPTED_SEEDS
        ]
        shortlist = {
            "config_digest": source["config_digest"],
            "source_seed_count": 20000,
            "taken_before_screen": len(source["candidates"]),
            "taken": len(accepted),
            "seeds": list(ACCEPTED_SEEDS),
            "review_seeds": list(REVIEW_SEEDS),
            "rejected": [
                {"seed": seed, "reason": reason} for seed, reason in rejected.items()
            ],
            "candidates": accepted,
        }
        (args.validation_dir / "phase3b_shortlist.json").write_text(
            json.dumps(shortlist, indent=2) + "\n", encoding="utf-8")
        if args.population:
            population = json.loads(args.population.read_text(encoding="utf-8"))
            compact = {key: value for key, value in population.items() if key != "records"}
            (args.validation_dir / "phase3b_population_20k.json").write_text(
                json.dumps(compact, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print(json.dumps({
            "seed": row["seed"],
            "duration": round(row["duration"], 3),
            "population": row["population"],
            "route": row["escape_route"],
            "outer_coop": row["cooperative_outer_breaks"],
            "triple_merge": row["readability"]["longest_triple_merge_seconds"],
            "largest_cluster": row["readability"]["largest_cluster"],
            "strict": row["strict_escalation"],
            "audio_eps": row["audio"]["events_per_second"],
            "max_poly": row["audio"]["max_polyphony"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

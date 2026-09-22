"""Reports and artifact helpers for the shell-escape visual proof.

Rendering itself stays in Godot.  This CLI measures the canonical documents,
compares a Godot audit to its source document, creates Shorts-control overlays,
and writes the candidate report used for the Phase 2A handoff.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Sequence

from satisfying.shell_playback import position_at
from satisfying.shell_visual import (
    REPRESENTATIVE_SEEDS,
    candidate_report,
    load_document,
    render_config,
    render_config_digest,
)
from satisfying.tile_safe_area import DEFAULT_SAFE_AREA, overlay_frame


def _write_json(path: str | os.PathLike[str], value: Any) -> None:
    target = os.fspath(path)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=1)
        handle.write("\n")


def _candidate_paths(folder: str | os.PathLike[str]) -> list[str]:
    root = os.fspath(folder)
    paths = [os.path.join(root, f"phase1_playback_seed{seed}.json")
             for seed in REPRESENTATIVE_SEEDS]
    missing = [path for path in paths if not os.path.exists(path)]
    if missing:
        raise SystemExit(f"missing representative playback documents: {missing}")
    return paths


def report(folder: str | os.PathLike[str],
           out: str | os.PathLike[str]) -> dict[str, Any]:
    candidates = [candidate_report(load_document(path)) for path in _candidate_paths(folder)]
    routes = sorted({candidate["final_method"] for candidate in candidates})
    bands = {
        "20-22": [c["seed"] for c in candidates if 20.0 <= c["duration"] < 22.0],
        "22-24": [c["seed"] for c in candidates if 22.0 <= c["duration"] < 24.0],
        "24-26": [c["seed"] for c in candidates if 24.0 <= c["duration"] <= 26.0],
    }
    result = {
        "format": "category3-shell-visual-report/1.0.0",
        "phase1_schema": "category3-test2-shell-escape/1.0.0",
        "phase1_config_digest": "7da0cbc80d595826",
        "render_config": render_config(),
        "render_config_digest": render_config_digest(),
        "representative_seeds": list(REPRESENTATIVE_SEEDS),
        "coverage": {
            "bands": bands,
            "final_methods": routes,
            "highest_near_misses": max(c["near_misses"] for c in candidates),
            "mixed_route_seed": 11929,
            "preview_seeds": [9589, 11929, 7699],
            "production_seed_selected": False,
        },
        "candidates": candidates,
        "all_safe_area_gates_pass": all(c["safe_area"]["gate_pass"] for c in candidates),
        "all_30fps_continuous": all(
            c["motion_30fps"]["trail_covers_frame_step"] for c in candidates
        ),
        "all_60fps_continuous": all(
            c["motion_60fps"]["trail_covers_frame_step"] for c in candidates
        ),
    }
    _write_json(out, result)
    return result


def compare_audit(document_path: str | os.PathLike[str],
                  audit_path: str | os.PathLike[str]) -> dict[str, Any]:
    document = load_document(document_path)
    with open(audit_path, encoding="utf-8") as handle:
        audit = json.load(handle)
    events = document["events"]
    source_times = [float(event["t"]) for event in events]
    source_kinds = [str(event["kind"]) for event in events]
    audit_times = [float(value) for value in audit["event_times"]]
    max_event_time_error = max(
        (abs(a - b) for a, b in zip(audit_times, source_times)), default=0.0
    )
    event_order_unchanged = (
        len(audit_times) == len(source_times)
        and audit_times == sorted(audit_times)
        and max_event_time_error < 2e-5
    )
    audit_panels = audit["panel_states"]
    source_panels = document["panel_states"]
    panel_states_unchanged = len(audit_panels) == len(source_panels) and all(
        int(a["shell_id"]) == int(b["shell_id"])
        and int(a["panel_id"]) == int(b["panel_id"])
        and abs(float(a["t"]) - float(b["t"])) < 2e-5
        for a, b in zip(audit_panels, source_panels)
    )
    samples_match = True
    worst_position_error = 0.0
    for sample in audit["samples"]:
        expected = position_at(document, float(sample["t"]))
        actual = sample["position"]
        error = ((expected[0] - actual[0]) ** 2 + (expected[1] - actual[1]) ** 2) ** 0.5
        worst_position_error = max(worst_position_error, error)
        samples_match = samples_match and error < 2e-5
    result = {
        "seed": document["seed"],
        "digest_matches": audit["digest"] == document["digest"],
        "schema_matches": audit["schema_version"] == document["schema_version"],
        "config_digest_matches": audit["config_digest"] == document["config_digest"],
        "event_order_unchanged": event_order_unchanged,
        "max_event_time_error": max_event_time_error,
        "event_kinds_unchanged": audit["event_kinds"] == source_kinds,
        "panel_states_unchanged": panel_states_unchanged,
        "sampled_positions_match": samples_match,
        "worst_position_error": worst_position_error,
    }
    result["pass"] = all(
        bool(value) for key, value in result.items()
        if key.endswith("matches") or key.endswith("unchanged")
    ) and samples_match
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Category 3 shell visual proof helpers")
    sub = parser.add_subparsers(dest="command", required=True)
    report_parser = sub.add_parser("report")
    report_parser.add_argument("--folder", required=True)
    report_parser.add_argument("--out", required=True)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--playback", required=True)
    audit_parser.add_argument("--audit", required=True)
    audit_parser.add_argument("--out")
    overlay_parser = sub.add_parser("overlay")
    overlay_parser.add_argument("--input", required=True)
    overlay_parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.command == "report":
        value = report(args.folder, args.out)
        print(f"{len(value['candidates'])} candidates -> {args.out}")
        return 0
    if args.command == "audit":
        value = compare_audit(args.playback, args.audit)
        if args.out:
            _write_json(args.out, value)
        print(json.dumps(value, indent=1))
        return 0 if value["pass"] else 1
    overlay_frame(args.input, args.out, DEFAULT_SAFE_AREA,
                  label=DEFAULT_SAFE_AREA.name)
    print(f"overlay -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

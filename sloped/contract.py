"""Checking the reconstruction against the record the locked branch left.

`sloped.layout` transcribes control points and `sloped.pathing` reimplements a
spline; both are hand ports of GDScript, and either could be subtly wrong in a
way that still produces a plausible course. This module is the independent
check: `docs/validation/sloped_course/physics_layout.json` was written *from
the built scene* by `course_scene.gd::_dump_physics` - the resampled
centrelines, the solved bank angles, the module yaws the placer worked out - so
agreeing with it is evidence about the port and not about the transcription.

Seven runs, 26 recorded centreline points each: 182 positions, plus each run's
length, drop, clear width, floor offset and bank extreme, plus the six module
anchors and the marble radius. A `Finding` for anything outside tolerance, in
the vocabulary `marble3d.validation` already uses.

The tolerances are not slack. The recorded points are the built path's own
samples rounded to three decimals by Godot's JSON writer, so a correct port
agrees to about 5e-4 and the budget is 2e-3. `bank_max_deg` is looser at 0.05
of a degree because it is the extreme of a smoothed series and the JSON
rounded it too.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from marble3d.validation import Finding

from sloped import layout
from sloped.pathing import auto_bank, build_path, path_length

__all__ = ["CONTRACT_PATH", "load", "check", "facts"]

CONTRACT_PATH = os.path.join("docs", "validation", "sloped_course", "physics_layout.json")

POINT_TOLERANCE = 2.0e-3
SCALAR_TOLERANCE = 5.0e-3
ANGLE_TOLERANCE = 0.05

# The one place the reconstruction is *meant* to disagree with the record, and
# by how much. Named here rather than absorbed into a looser tolerance, because
# a tolerance wide enough to hide this would be wide enough to hide the next
# thing, and the value of the contract is that a gap is a finding.
#
# Orange's three tail control heights were redistributed to stop the run
# climbing; `sloped.layout` carries the measurement. The plan curve is
# untouched, so the deviation is in height alone, and the recorded 26-point
# centreline moves only at the samples that fall in that tail. `drop` is
# unchanged because both endpoints are.
#
# A deviation still has a budget. If the reconstruction ever moves further than
# this it is a finding again.
DEVIATIONS: dict[tuple[str, str], tuple[float, str]] = {
    ("orange", "centreline"): (
        0.16,
        "orange's tail heights are redistributed so the run stops climbing "
        "(sloped.layout); plan unchanged, height moves by at most 0.145",
    ),
    # And the run is 0.0076 shorter for it, because a tail that no longer
    # overshoots in height is a shorter curve through the same plan points.
    ("orange", "length"): (
        0.01,
        "the redistributed tail is 0.0076 shorter than the overshooting one",
    ),
}


def load(path: str = CONTRACT_PATH) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _thinned(path: list, count: int) -> list:
    """`course_scene.gd::_thinned` - every (n-1)/(count-1)th sample, rounded."""
    out = []
    for step in range(count):
        index = min(max(int(round(step * (len(path) - 1) / (count - 1))), 0), len(path) - 1)
        out.append(path[index])
    return out


def check(contract: dict[str, Any] | None = None) -> list[Finding]:
    """Every disagreement between the reconstruction and the record."""
    contract = contract if contract is not None else load()
    findings: list[Finding] = []

    def report(name: str, subject: str, detail: str) -> None:
        findings.append(Finding(check=name, subject=subject, detail=detail))

    if contract.get("layout") != layout.LAYOUT_KEY:
        report("layout", "course", f"contract is layout {contract.get('layout')!r}")
    if contract.get("title") != layout.TITLE:
        report("layout", "course", f"contract is titled {contract.get('title')!r}")

    recorded_radius = float(contract["marble"]["radius"])
    if abs(recorded_radius - layout.MARBLE_RADIUS) > 1e-9:
        report(
            "marble",
            "radius",
            f"contract says {recorded_radius}, layout says {layout.MARBLE_RADIUS}",
        )

    by_name = {str(entry["name"]): entry for entry in contract["runs"]}
    if set(by_name) != set(layout.run_names()):
        report(
            "runs",
            "set",
            f"contract has {sorted(by_name)}, layout has {sorted(layout.run_names())}",
        )

    for spec in layout.RUNS:
        name = str(spec["name"])
        recorded = by_name.get(name)
        if recorded is None:
            continue
        path, banks, _tangents, _widths = build_path(
            spec["controls"], float(spec["bank_gain"]), float(spec["bank_max"])
        )

        worst = 0.0
        worst_at = -1
        for index, (mine, theirs) in enumerate(zip(_thinned(path, 26), recorded["centreline"])):
            gap = math.dist(mine, theirs)
            if gap > worst:
                worst, worst_at = gap, index
        allowed, why = DEVIATIONS.get((name, "centreline"), (POINT_TOLERANCE, ""))
        if worst > allowed:
            report(
                "centreline",
                name,
                f"sample {worst_at} of 26 is {worst:.5f} from the recorded point "
                f"(budget {allowed})" + (f" - {why}" if why else ""),
            )

        pairs = (
            (
                "length",
                path_length(path),
                float(recorded["length"]),
                DEVIATIONS.get((name, "length"), (SCALAR_TOLERANCE, ""))[0],
            ),
            ("drop", path[0][1] - path[-1][1], float(recorded["drop"]), SCALAR_TOLERANCE),
            (
                "clear_width",
                layout.HERO_CLEAR_WIDTH * float(spec["scale"]),
                float(recorded["clear_width"]),
                SCALAR_TOLERANCE,
            ),
            (
                "floor_offset",
                layout.FLOOR_Y * float(spec["scale"]),
                float(recorded["floor_offset"]),
                SCALAR_TOLERANCE,
            ),
            (
                "profile_scale",
                float(spec["scale"]),
                float(recorded["profile_scale"]),
                1e-9,
            ),
            (
                "bank_max_deg",
                max(abs(math.degrees(value)) for value in banks),
                float(recorded["bank_max_deg"]),
                ANGLE_TOLERANCE,
            ),
        )
        for label, mine, theirs, budget in pairs:
            if abs(mine - theirs) > budget:
                report(
                    label,
                    name,
                    f"reconstruction {mine:.4f} against recorded {theirs:.4f} "
                    f"(budget {budget})",
                )

        for label, key in (("entry_socket", "origin"), ("exit_socket", None)):
            theirs = recorded[label]["at"]
            mine = path[0] if label == "entry_socket" else path[-1]
            gap = math.dist(mine, theirs)
            if gap > POINT_TOLERANCE:
                report(label, name, f"{gap:.5f} from the recorded socket position")

    anchors = {str(entry["name"]).lower(): entry["anchor"] for entry in contract["modules"]}
    # The layout table calls it "mix" and the built node is named "Mixer";
    # `_modules` places it from the table and names it from the builder, so the
    # two spellings are the same anchor and only the key differs.
    aliases = {"mix": "mixer"}
    for key, point in layout.NODES.items():
        theirs = anchors.get(aliases.get(key, key))
        if theirs is None:
            report("module", key, "the contract records no module with this anchor")
            continue
        gap = math.dist(point, theirs)
        if gap > 1e-6:
            report("module", key, f"anchor is {gap:.5f} from the recorded one")

    return findings


def facts(contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the check measured, for a report that has to quote a number."""
    contract = contract if contract is not None else load()
    by_name = {str(entry["name"]): entry for entry in contract["runs"]}
    out: dict[str, Any] = {"runs": {}}
    worst_point = 0.0
    for spec in layout.RUNS:
        name = str(spec["name"])
        path, banks, _t, _w = build_path(
            spec["controls"], float(spec["bank_gain"]), float(spec["bank_max"])
        )
        recorded = by_name[name]
        gaps = [
            math.dist(mine, theirs)
            for mine, theirs in zip(_thinned(path, 26), recorded["centreline"])
        ]
        worst_point = max(worst_point, max(gaps))
        out["runs"][name] = {
            "samples": len(path),
            "length": round(path_length(path), 4),
            "recorded_length": recorded["length"],
            "worst_centreline_gap": round(max(gaps), 6),
            "bank_max_deg": round(max(abs(math.degrees(v)) for v in banks), 4),
            "recorded_bank_max_deg": recorded["bank_max_deg"],
        }
    out["worst_centreline_gap"] = round(worst_point, 6)
    out["per_run_centreline_gap"] = {
        name: block["worst_centreline_gap"] for name, block in out["runs"].items()
    }
    # The same number with the named deviations left out, which is what says
    # whether the *port* is still exact. A report that quoted only the first
    # would read as though the reconstruction had drifted.
    out["worst_centreline_gap_excluding_deviations"] = round(
        max(
            (
                gap
                for name, gap in out["per_run_centreline_gap"].items()
                if (name, "centreline") not in DEVIATIONS
            ),
            default=0.0,
        ),
        6,
    )
    out["deviations"] = {
        f"{name}.{what}": {"budget": budget, "why": why}
        for (name, what), (budget, why) in DEVIATIONS.items()
    }
    out["total_hero_length"] = round(
        sum(out["runs"][name]["length"] for name in ("launch", "leg1", "leg2", "leg3", "final")), 4
    )
    out["blue_route_length"] = round(out["total_hero_length"] + out["runs"]["blue"]["length"], 4)
    out["orange_route_length"] = round(out["total_hero_length"] + out["runs"]["orange"]["length"], 4)
    return out

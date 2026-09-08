"""Validate the radial start's geometry before any marble is run.

    python tools/sloped_radial_check.py
    python tools/sloped_radial_check.py --json out.json

Section 4 of the V1.4 brief asks for a per-guide report with explicit
tolerances, before trials. This prints it, plus four things it does not ask for
and needs anyway:

* **the two exact invariants.** Drop from the pan to the trough, and radius
  from the drain at rest. Both are single derived numbers rather than eight, so
  both spreads should be exactly zero, and a non-zero one means an edit has
  broken the derivation.
* **lane separation.** The guides are grooves, not channels, so what matters is
  the least distance between two centrelines anywhere - and whether a rib fits
  between them there.
* **rim clearance.** A guide that strays inside the trough's rim before its own
  delivery bearing drops its marble into the ring at the wrong place.
* **the mesh and the probes**, the same `check_mesh` and floor probes every
  other module in the tree answers.

The chute-era checks are gone with the chutes: there is no pairwise chute
isolation to measure because there are no walls to isolate, and no foreign-cup
containment because there are no cups.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marble3d.validation import check_mesh  # noqa: E402
from sloped import layout  # noqa: E402
from sloped.radial import RadialStart, guide_table  # noqa: E402
from sloped.track import TrackRun  # noqa: E402

# A marble's own width plus a rib. Two centrelines closer than this share one
# groove, and the rib between them has nowhere to stand.
LANE_NEEDED = 2.0 * layout.MARBLE_RADIUS + 0.07
# The grade band. Below the first a marble stops - the basin measured 0.9
# degrees moving nothing and 7.9 working - and above the second the guide is a
# fall onto the ring rather than a delivery.
GRADE_MIN = 8.0
GRADE_MAX = 42.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    options = parser.parse_args(argv)

    launch = TrackRun("launch")
    start = RadialStart("start", launch)
    table = guide_table(start)
    described = start.describe()
    heights = described["heights"]

    print("RadialStart geometry, layout units")
    print(
        "  pan {rest_floor}  trough rim {trough_floor}  at rest {paddle_floor}  "
        "drain lip {drain_lip}  launch entry {exit_y}".format(**heights)
    )
    print(
        f"  trough radius {start.TROUGH_R}  resting radius "
        f"{described['rest_radius']}  drain radius {start.DRAIN_R}  "
        f"lift {described['lift']}  release {start.RELEASE}s"
    )
    exit_run = math.hypot(
        start.exit_local[0], start.exit_local[2] - start.DISH_Z + start.CHUTE_LEAD
    )
    exit_drop = (start.drain_lip - (0.24 if start.FUNNEL else 0.30)) - start.exit_local[1]
    print(
        f"  exit chute {exit_drop:.2f} over {exit_run:.2f} = "
        f"{math.degrees(math.atan2(exit_drop, exit_run)):.1f} deg"
    )
    print()

    header = (
        f"{'bay':>3} {'slot':>4} {'bearing':>8} {'sweep':>7} {'length':>7} "
        f"{'apron':>6} {'drop':>5} {'mean':>6} {'gmin':>6} {'gmax':>6} "
        f"{'curve':>6} {'bank':>5} {'entryT':>7} {'outT':>7} {'roll s':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in table["rows"]:
        print(
            f"{row['bay']:>3} {row['slot']:>4} {row['bearing_deg']:>8.1f} "
            f"{row['sweep_deg']:>7.1f} {row['length']:>7.3f} "
            f"{row['apron_length']:>6.3f} {row['drop']:>5.2f} "
            f"{row['mean_grade_deg']:>6.2f} {row['min_grade_deg']:>6.2f} "
            f"{row['max_grade_deg']:>6.2f} {row['min_curve']:>6.2f} "
            f"{row['bank_needed_deg']:>5.1f} {row['entry_tangent_deg']:>7.1f} "
            f"{row['delivery_tangent_deg']:>7.1f} {row['roll_seconds']:>7.3f}"
        )
    print("-" * len(header))
    spread = table["spread"]
    print(
        f"  drop spread {spread['drop_spread']:.9f}   delivery radius spread "
        f"{spread['delivery_radius_spread']:.9f}   resting radius "
        f"{spread['rest_radius']:.6f}"
    )
    print(
        f"  length {spread['length'][0]:.3f}..{spread['length'][1]:.3f}, spread "
        f"{spread['length_spread']:.3f}, ratio {spread['length_ratio']:.2f}"
    )
    print(
        f"  local grade {spread['grade'][0]:.1f}..{spread['grade'][1]:.1f} deg, "
        f"mean {spread['mean_grade'][0]:.1f}..{spread['mean_grade'][1]:.1f}"
    )
    print(
        f"  roll {spread['roll_seconds'][0]:.2f}..{spread['roll_seconds'][1]:.2f}s, "
        f"release margin {spread['release_margin']:+.2f}s"
    )
    print(
        f"  running lane pair {spread['worst_lane_pair'][0]} at "
        f"{spread['worst_lane_pair'][1]:.3f} ({LANE_NEEDED:.2f} needed)   "
        f"rim slack {spread['trough_rim_slack']:+.3f}   apron width "
        f"{spread['apron_width']:.2f}"
    )
    print(
        f"  closest pass to another route's delivery point: "
        f"{spread['worst_delivery_gap'][1]:.3f} "
        f"(route {spread['worst_delivery_gap'][0][0]} past "
        f"{spread['worst_delivery_gap'][0][1]}'s, "
        f"{2.0 * layout.MARBLE_RADIUS:.2f} = two marbles touching)"
    )
    print(
        f"  groove-only curvature margin {spread['groove_margin']:.2f}, so the "
        f"apron wants up to {spread['bank_needed_deg']:.0f} deg of bank"
    )

    # --- the tolerances, stated ------------------------------------------
    findings: list[str] = []
    if spread["drop_spread"] > 1e-9:
        findings.append(f"drop spread {spread['drop_spread']:.9f} is not zero")
    if spread["delivery_radius_spread"] > 1e-9:
        findings.append(
            f"delivery radius spread {spread['delivery_radius_spread']:.9f} is not zero"
        )
    if spread["release_margin"] < 0.30:
        findings.append(
            f"release at {start.RELEASE}s leaves only "
            f"{spread['release_margin']:.2f}s over the slowest guide"
        )
    for row in table["rows"]:
        if row["min_grade_deg"] < GRADE_MIN:
            findings.append(
                f"bay {row['bay']} guide falls to {row['min_grade_deg']:.1f} deg "
                f"and will stall"
            )
        if row["max_grade_deg"] > GRADE_MAX:
            findings.append(
                f"bay {row['bay']} guide reaches {row['max_grade_deg']:.1f} deg, a fall"
            )
        if abs(row["entry_tangent_deg"] - 90.0) > 12.0:
            findings.append(
                f"bay {row['bay']} leaves the line at {row['entry_tangent_deg']:.0f} "
                f"deg rather than downhill"
            )
    if spread["worst_lane_pair"][1] < LANE_NEEDED:
        pair = spread["worst_lane_pair"][0]
        findings.append(
            f"guides {pair[0]} and {pair[1]} pass within "
            f"{spread['worst_lane_pair'][1]:.3f}, so no rib fits between them there"
        )
    if spread["worst_delivery_gap"][1] < 2.0 * layout.MARBLE_RADIUS - 0.06:
        pair = spread["worst_delivery_gap"][0]
        findings.append(
            f"route {pair[0]} passes {spread['worst_delivery_gap'][1]:.3f} from "
            f"route {pair[1]}'s delivery point, closer than two marbles"
        )
    if spread["trough_rim_slack"] is not None and spread["trough_rim_slack"] < 0.05:
        findings.append(
            f"a guide runs {spread['trough_rim_slack']:.3f} inside the trough rim "
            f"before its own delivery bearing"
        )
    if exit_drop / max(exit_run, 1e-6) > math.tan(math.radians(GRADE_MAX)):
        findings.append(f"the exit chute is a {exit_drop / exit_run:.2f} grade fall")

    # --- no hidden uphill anywhere along a guide --------------------------
    worst_rise = 0.0
    for index in range(layout.BAYS):
        previous = None
        for step in range(241):
            point = start.guide_point(index, step / 240.0)
            if previous is not None:
                worst_rise = max(worst_rise, point[1] - previous[1])
            previous = point
    print(f"  worst uphill step along any guide {worst_rise:+.6f}")
    if worst_rise > 1e-6:
        findings.append(f"a guide climbs {worst_rise:.4f} somewhere")

    # --- mesh and probes --------------------------------------------------
    print()
    mesh = start.local_colliders()[0]
    mesh_findings = check_mesh(mesh, expect_components=None)
    print(
        f"mesh: {len(mesh.vertices)} vertices, {len(mesh.indices) // 3} triangles, "
        f"{len(mesh_findings)} findings"
    )
    for finding in mesh_findings[:8]:
        print(f"  {finding}")
    if mesh_findings:
        findings.append(f"{len(mesh_findings)} mesh findings")
    probes = start.local_probes()
    print(f"probes: {len(probes)} declared   actuators: {len(start.local_actuators())}")

    print()
    if findings:
        print(f"FINDINGS ({len(findings)}):")
        for finding in findings:
            print(f"  - {finding}")
    else:
        print(
            "no findings: drop and resting radius exact, grades in band, "
            "lanes clear, rim clear, mesh clean"
        )

    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(
            json.dumps(
                {
                    "start_kind": start.START_KIND,
                    "lift": described["lift"],
                    "heights": heights,
                    "rest_radius": described["rest_radius"],
                    "delivery_bearings": described["delivery_bearings"],
                    "guides": table["rows"],
                    "spread": spread,
                    "exit_chute": {
                        "run": round(exit_run, 4),
                        "drop": round(exit_drop, 4),
                        "grade_deg": round(
                            math.degrees(math.atan2(exit_drop, exit_run)), 3
                        ),
                    },
                    "worst_uphill_step": round(worst_rise, 6),
                    "lane_needed": round(LANE_NEEDED, 4),
                    "mesh": {
                        "vertices": len(mesh.vertices),
                        "triangles": len(mesh.indices) // 3,
                        "findings": [str(f) for f in mesh_findings],
                    },
                    "findings": findings,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {options.json}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

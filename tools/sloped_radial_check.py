"""Validate the radial start's geometry before any marble is run.

    python tools/sloped_radial_check.py
    python tools/sloped_radial_check.py --json out.json

Section 5 of the V1.4 brief asks for a per-bay feeder report with an explicit
tolerance, before trials. This prints it, and three things it does not ask for
and needs anyway:

* **isolation** - the minimum three-dimensional distance between every pair of
  chute centrelines, against the width a chute actually occupies. Eight hidden
  channels that cross in plan are only isolated if they are separated in
  height, and "they should be" is not a measurement.
* **containment** - every chute's floor against the dish rim and against the
  cups it does not own, so a chute bridging the dish is above it rather than
  through it.
* **the mesh and the probes** - the same `check_mesh` and cradle probes every
  other module in the tree answers.
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
from sloped.radial import RadialStart, feeder_table  # noqa: E402
from sloped.scale import to_sim  # noqa: E402
from sloped.track import TrackRun  # noqa: E402

# What a chute occupies: the cradle's clear width plus a wall each side. Two
# centrelines closer than this in 3D are the same channel.
CHUTE_WIDTH = 2.0 * (RadialStart.CUP_HALF + 0.10)
# And how much height clears a chute standing over another one: the wall it
# carries plus the floor structure under the one above.
CHUTE_HEIGHT = RadialStart.FEEDER_WALL + 0.14


def _dense(samples, step: float = 0.05):
    """Resample a chute's centreline finely, so a crossing cannot be missed."""
    out = []
    for index in range(len(samples) - 1):
        a, b = samples[index], samples[index + 1]
        span = math.dist(a, b)
        count = max(1, int(span / step))
        for k in range(count):
            t = k / count
            out.append(tuple(a[axis] + (b[axis] - a[axis]) * t for axis in range(3)))
    out.append(tuple(samples[-1]))
    return out


def _separated(a, b) -> tuple[float, float, tuple]:
    """Worst approach between two centrelines, as (plan, height, at).

    Two channels are isolated if at every point *either* the plan distance
    exceeds one channel width *or* the height difference exceeds one channel
    height. So the worst case is the point that minimises the slack in both at
    once, and that is what is reported.
    """
    worst = (1e9, 1e9, None)
    worst_slack = 1e9
    for pa in a:
        for pb in b:
            plan = math.hypot(pa[0] - pb[0], pa[2] - pb[2])
            rise = abs(pa[1] - pb[1])
            slack = max(plan / CHUTE_WIDTH, rise / CHUTE_HEIGHT)
            if slack < worst_slack:
                worst_slack = slack
                worst = (plan, rise, pa)
    return worst[0], worst[1], worst[2], worst_slack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--step", type=float, default=0.06)
    options = parser.parse_args(argv)

    launch = TrackRun("launch")
    start = RadialStart("start", launch)
    table = feeder_table(start)

    print("RadialStart geometry, layout units")
    heights = start.describe()["heights"]
    print(
        "  shelf floor {shelf_floor}  port floor {port_floor}  "
        "drain lip {drain_lip}  launch entry {exit_y}".format(**heights)
    )
    print(
        f"  port radius {start.PORT_R}  drain radius {start.DRAIN_R}  "
        f"lift {start.describe()['lift']}  port release {start.PORT_RELEASE}s"
    )
    print()
    header = (
        f"{'bay':>3} {'slot':>4} {'port deg':>8} {'length':>7} {'drop':>6} "
        f"{'grade':>7} {'worst':>7} {'shape':>6} {'radius':>7} {'fall s':>7}"
    )
    print(header)
    print("-" * len(header))
    for row in table["rows"]:
        print(
            f"{row['bay']:>3} {row['slot']:>4} {row['port_deg']:>8.1f} "
            f"{row['length']:>7.3f} {row['drop']:>6.3f} {row['grade_deg']:>7.2f} "
            f"{row['steepest_deg']:>7.2f} {row['shape']:>6.2f} "
            f"{row['port_radius']:>7.3f} {row['fall_seconds']:>7.3f}"
        )
    print("-" * len(header))
    spread = table["spread"]
    print(
        f"  drop spread {spread['drop_spread']:.6f}   "
        f"radius spread {spread['radius_spread']:.6f}   "
        f"length spread {spread['length_spread']:.3f}"
    )
    print(
        f"  fall {spread['fall_seconds'][0]:.2f}..{spread['fall_seconds'][1]:.2f}s, "
        f"release margin {spread['release_margin']:+.2f}s"
    )

    # --- the tolerances, stated ------------------------------------------
    findings: list[str] = []
    if spread["drop_spread"] > 1e-6:
        findings.append(f"drop spread {spread['drop_spread']:.6f} is not zero")
    if spread["radius_spread"] > 1e-6:
        findings.append(f"port radius spread {spread['radius_spread']:.6f} is not zero")
    if spread["release_margin"] < 0.35:
        findings.append(
            f"port release {start.PORT_RELEASE}s leaves only "
            f"{spread['release_margin']:.2f}s over the slowest chute"
        )
    for row in table["rows"]:
        if row["grade_deg"] < 9.0:
            findings.append(f"bay {row['bay']} chute at {row['grade_deg']:.1f} deg will stall")
        if row["steepest_deg"] > 46.0:
            findings.append(
                f"bay {row['bay']} chute reaches {row['steepest_deg']:.1f} deg, a drop"
            )

    # --- isolation --------------------------------------------------------
    print()
    print("chute isolation, worst approach per pair (plan / rise / slack)")
    tracks = {f["bay"]: _dense(f["samples"], options.step) for f in start.feeders()}
    worst_overall = (1e9, None)
    pairs = []
    for a in range(layout.BAYS):
        for b in range(a + 1, layout.BAYS):
            plan, rise, at, slack = _separated(tracks[a], tracks[b])
            pairs.append((slack, a, b, plan, rise, at))
            if slack < worst_overall[0]:
                worst_overall = (slack, (a, b, plan, rise, at))
    pairs.sort()
    for slack, a, b, plan, rise, at in pairs[:6]:
        flag = "  <-- too close" if slack < 1.0 else ""
        print(
            f"  {a}-{b}: plan {plan:5.2f} ({CHUTE_WIDTH:.2f} needed)  "
            f"rise {rise:5.2f} ({CHUTE_HEIGHT:.2f} needed)  slack {slack:4.2f}{flag}"
        )
    if worst_overall[0] < 1.0:
        a, b, plan, rise, at = worst_overall[1]
        findings.append(
            f"chutes {a} and {b} are not isolated: plan {plan:.2f}, rise {rise:.2f}"
        )

    # --- containment: a chute over the dish must be over it ---------------
    print()
    inner = start.port_floor - start.CUP_TILT
    rim_top = inner + start.RIM_RISE
    cup_top = start.port_floor + start.CUP_WALL
    worst_rim = 1e9
    worst_cup = 1e9
    for bay, track in tracks.items():
        own = start.port_angle(bay)
        for point in track:
            radius = math.hypot(point[0], point[2] - start.DISH_Z)
            if radius > start.RIM_R + 0.2:
                continue
            # Inside the rim: the floor has to be above the rim's top, unless
            # this is the chute's own last approach into its own cup.
            deg = math.degrees(math.atan2(point[2] - start.DISH_Z, point[0])) % 360.0
            own_arc = ((own - deg) % 360.0) <= start.CUP_ARC + 12.0
            if own_arc and radius > start.PORT_R - start.CUP_HALF - 0.2:
                continue
            worst_rim = min(worst_rim, point[1] - rim_top)
            if radius > start.PORT_R - start.CUP_HALF - 0.2:
                worst_cup = min(worst_cup, point[1] - cup_top)
    print(
        f"containment: lowest chute floor over the rim {worst_rim:+.3f}, "
        f"over a foreign cup {worst_cup:+.3f}"
    )
    if worst_rim < 0.10:
        findings.append(f"a chute floor is only {worst_rim:.3f} over the dish rim")
    if worst_cup < 0.10:
        findings.append(f"a chute floor is only {worst_cup:.3f} over a foreign cup")

    # --- mesh and probes --------------------------------------------------
    print()
    mesh = start.local_colliders()[0]
    # `expect_components=None` because this module *is* many pieces - the
    # shelf, eight chutes, eight cups, the dish and seven ridge tubes.
    mesh_findings = check_mesh(mesh, expect_components=None)
    print(
        f"mesh: {len(mesh.vertices)} vertices, {len(mesh.indices) // 3} triangles, "
        f"{len(mesh_findings)} findings"
    )
    for finding in mesh_findings[:8]:
        print(f"  {finding}")
    probes = start.local_probes()
    print(f"probes: {len(probes)} declared")

    print()
    if findings:
        print(f"FINDINGS ({len(findings)}):")
        for finding in findings:
            print(f"  - {finding}")
    else:
        print("no findings: drops and radii equal, chutes isolated, dish clear")

    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(
            json.dumps(
                {
                    "heights": heights,
                    "feeders": table["rows"],
                    "spread": table["spread"],
                    "isolation": [
                        {
                            "pair": [a, b],
                            "plan": round(plan, 4),
                            "rise": round(rise, 4),
                            "slack": round(slack, 4),
                        }
                        for slack, a, b, plan, rise, _at in pairs
                    ],
                    "containment": {
                        "over_rim": round(worst_rim, 4),
                        "over_foreign_cup": round(worst_cup, 4),
                    },
                    "mesh_findings": [str(f) for f in mesh_findings],
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

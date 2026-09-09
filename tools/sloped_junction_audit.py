"""Audit the merge junction as one surface, on both running edges.

    python tools/sloped_junction_audit.py
    python tools/sloped_junction_audit.py --routes both --json out.json
    python tools/sloped_junction_audit.py --basins-only

Section 3 of the V1.12 brief asks for the blue tail, the orange tail, the merge
apron and the final entry to be validated as one continuous physical junction -
no floor step, no uphill lip on a nominally downhill transition, tangent
continuity, controlled roll, marble clearance, no collider overlap producing a
trap, no unsupported floor, no guard standing inside the running surface - and
says how:

    DO NOT inspect centreline height alone. Explicitly inspect BOTH running
    edges through the entire transition.

So every number here is per lateral line, and the centreline is reported next
to the edges rather than instead of them. `sloped.junction` has the mechanics.

Three things this reports that nothing else in the tree did:

* **the basin survey over the branch lobes.** `tools/sloped_pocket_survey.py`
  covers `CHAIN + ("final",)`, so `blue` and `orange` were never surveyed. Both
  carry a roll-reversal basin of the same shape as the one V1.11 fixed on leg2,
  and deeper.
* **which module owns the floor**, station by station. The merge apron is a
  height field laid over two swept channels and the highest of the three is
  what a marble rests on, which is not always the channel.
* **holes.** A station with no surface under it at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sloped.course import sloped_course  # noqa: E402
from sloped.junction import (  # noqa: E402
    FRACTIONS,
    SurfaceIndex,
    branch_frame,
    climb_survey,
    reference_frame,
    walk_line,
)

# The junction, as stations. Wide enough to carry the whole roll reversal on
# each branch tail, and far enough down the sprint to clear the apron's front
# edge and the guard window that closes at `final[14]`.
BLUE_WALK = [("blue", i) for i in range(86, 118)] + [("final", i) for i in range(0, 22)]
ORANGE_WALK = [("orange", i) for i in range(86, 118)] + [("final", i) for i in range(0, 22)]

OWNERS = ("blue", "blue_lead", "orange", "orange_lead", "merge", "final", "finish")


def _print_walk(title: str, walk) -> None:
    print()
    print(f"--- {title} " + "-" * max(0, 66 - len(title)))
    print("floor Y, grade in percent of horizontal travel (POSITIVE = A CLIMB), owner")
    lines = [label for _f, label in FRACTIONS]
    print(f"{'station':>12}" + "".join(f"{label:>22}" for label in lines))
    by_station: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for reading in walk.readings:
        if reading.station not in by_station:
            by_station[reading.station] = {}
            order.append(reading.station)
        by_station[reading.station][reading.line] = reading
    for station in order:
        cells = []
        for label in lines:
            reading = by_station[station].get(label)
            if reading is None or reading.floor is None:
                cells.append("      NO FLOOR       ")
                continue
            grade = "      " if reading.grade is None else f"{reading.grade:+6.1f}"
            flag = "!" if reading.grade is not None and reading.grade > 0.5 else " "
            ledge = "L" if reading.ledge is not None else " "
            cells.append(f"{reading.floor:8.3f}{grade}%{flag}{ledge} {reading.owner[:5]:<5}")
        print(f"{station:>12}" + "".join(f"{cell:>22}" for cell in cells))
    print(
        f"  findings: {len(walk.holes)} holes, {len(walk.climbs)} climbs, "
        f"{len(walk.ledges)} ledges, {len(walk.tight)} tight clearances"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", default="both", choices=("blue", "both"))
    parser.add_argument("--basins-only", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    machine = sloped_course(routes=args.routes)
    runs = machine.runs
    report: dict[str, object] = {"routes": args.routes}

    print("=" * 88)
    print(f"MERGE JUNCTION AUDIT - routes={args.routes}")
    print("=" * 88)

    # --- the basin survey, over every run the junction is made of -------
    print()
    print("--- closed basins on each run's own surface " + "-" * 33)
    print("deepest climb above a running minimum, in simulation units, per lateral fraction")
    print("and the forward speed a rolling marble needs to leave it")
    fractions = (0.0, 0.4, 0.55, 0.7, 0.85, 0.95)
    print(f"{'run':<13}" + "".join(f"{f:>9.2f}" for f in fractions) + "    worst  needs  @sample")
    basins = {}
    for name in ("launch", "leg1", "leg2", "leg3", "blue_lead", "blue", "orange_lead", "orange", "final"):
        if name not in runs:
            continue
        survey = climb_survey(runs[name], fractions=fractions)
        basins[name] = survey
        row = []
        for f in fractions:
            keys = [f"{f:+.2f}"] if f == 0.0 else [f"{-f:+.2f}", f"{f:+.2f}"]
            row.append(max(survey["lines"][k]["climb"] for k in keys))
        worst = survey["worst"]
        print(
            f"{name:<13}" + "".join(f"{v:>9.4f}" for v in row)
            + f"  {worst['climb']:>7.4f} {worst['escape_speed']:>6.2f}  {worst['at_sample']}"
        )
    report["basins"] = basins
    print()
    print("  A basin is only a trap for a marble that has already lost its speed - which is")
    print("  what a collision in the merge does. leg2's was 0.0685 before V1.11 fixed it.")

    if not args.basins_only:
        index = SurfaceIndex(machine, OWNERS)
        print(f"\n  {len(index.tris)} triangles indexed over {len(OWNERS)} modules")

        # --- the endpoint frames the rebuild is derived from ------------
        sprint = reference_frame(runs["final"], 0)
        print()
        print("--- endpoint frames, in the sprint's own frame at its entry " + "-" * 17)
        print("(along down the sprint, across to its side, rise above its contact point)")
        frames = {}
        wanted = [("blue", len(runs["blue"].sim_path) - 1), ("final", 0)]
        if "orange" in runs:
            wanted.insert(1, ("orange", len(runs["orange"].sim_path) - 1))
        for name, sample in wanted:
            frame = branch_frame(runs[name], sample, reference=sprint)
            frames[name] = frame
            local = frame["in_reference"]
            print(
                f"  {name+'['+str(sample)+']':<14} contact {local['contact']}"
                f"  tangent {local['tangent']}"
            )
            print(
                f"  {'':<14} heading {frame['heading_deg']:+8.2f}  bank {frame['bank_deg']:+7.2f}"
                f"  grade {frame['grade_pct']:+7.2f}%  half {frame['half_width']:.3f}"
                f"  scale {frame['scale']}"
            )
            for edge in ("west_running", "east_running", "west_guard", "east_guard"):
                print(f"  {'':<14}   {edge:<14} {local['edges'][edge]}")
        report["frames"] = frames
        turn = frames["final"]["heading_deg"] - frames["blue"]["heading_deg"]
        print(f"  blue -> sprint: {turn:+.2f} degrees of heading change")
        if "orange" in frames:
            turn = frames["final"]["heading_deg"] - frames["orange"]["heading_deg"]
            print(f"  orange -> sprint: {turn:+.2f} degrees ({abs(turn) - 360:+.2f} the other way)")

        blue = walk_line(index, runs, BLUE_WALK)
        _print_walk("blue tail -> merge -> final sprint", blue)
        report["blue_walk"] = blue.to_json()
        walks = [("blue", blue)]
        if "orange" in runs:
            orange = walk_line(index, runs, ORANGE_WALK)
            _print_walk("orange tail -> merge -> final sprint", orange)
            report["orange_walk"] = orange.to_json()
            walks.append(("orange", orange))

        print()
        print("--- verdict " + "-" * 65)
        for name, walk in walks:
            state = "CLEAN" if walk.clean() else "DEFECTS"
            print(
                f"  {name:<8} {state:<8} holes {len(walk.holes):3d}  climbs {len(walk.climbs):3d}"
                f"  ledges {len(walk.ledges):3d}  tight {len(walk.tight):3d}"
            )
            for reading in walk.holes[:6]:
                print(f"      HOLE  {reading.station} {reading.line}")
            worst = walk.worst_climb()
            if worst is not None:
                print(
                    f"      worst climb {worst.grade:+.1f}% at {worst.station} {worst.line}"
                    f" (owner {worst.owner})"
                )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

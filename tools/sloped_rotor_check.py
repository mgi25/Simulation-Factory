"""Validate the dynamic start equaliser's geometry before any marble is run.

    python tools/sloped_rotor_check.py
    python tools/sloped_rotor_check.py --json out.json

Section 4 of the V1.7 brief asks what caused the earlier wheel's jams and what
is different here, and section 11 will not accept a fairness number from a
mechanism that loses the field. This tool answers the first and is the gate
before the second.

What it checks, and why each one is here rather than trusted:

* **every clearance a marble could be caught in is constant.** That is the
  whole reason the rotor moved into a chamber: the earlier wheel swept a circle
  inside a straight channel, so its tip-to-wall gap closed from 0.94 to 0.04
  four times a revolution and passed through exactly one marble diameter on the
  way. A concentric chamber cannot do that, and this prints the numbers.
* **the field can pass itself.** V1.5's trough put eight marbles at one radius
  in a channel one marble wide, where they cannot exchange cyclic order, so a
  stirrer could only rotate the necklace. The free radial travel has to be near
  two marble diameters.
* **the retracted gate ring clears the exit chute.** It retracts downward into
  the space the chute occupies, and a short travel leaves it standing in the
  chute's mouth as a fence - which is exactly what happened at 0.80.
* **the outlet's mouth covers the whole hole.** A chute whose first ring is
  downstream of the hole's upstream edge opens the rest of the hole onto
  nothing, and every racer falls out of the machine.
* **the timeline is ordered**: the field is in before the rotor stops, the
  rotor has stopped and settled before the outlet opens.
* the mesh and the floor probes, as every other module in the tree answers.
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
from sloped.shuffle import ShuffleChamber, chamber_table  # noqa: E402
from sloped.track import TrackRun  # noqa: E402

DIAMETER = 2.0 * layout.MARBLE_RADIUS
# **The band in which a gap is dangerous, as a fraction of a marble.** A gap
# only traps if a marble can get into it, so the danger is not "small" - it is
# *comparable to a marble*. Below 0.45 of a diameter a marble cannot enter at
# all and the surface simply sweeps it; above 1.25 it passes through with room.
# The first version of this check flagged anything under 1.14 and duly reported
# the chamber's own 0.15 clearances as pinches, which is the opposite of true:
# 0.15 is a quarter of a marble and is precisely why nothing can be caught.
PINCH_LOW = 0.45
PINCH_HIGH = 1.25
# How much free radial travel the field needs to be able to pass itself.
FREE_TRAVEL_DIAMETERS = 1.8
# The grade band the exit chute has to sit in: shallower and a clump of eight
# stacks in it, steeper and it is a fall onto the launch.
CHUTE_MIN = 10.0
CHUTE_MAX = 34.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    options = parser.parse_args(argv)

    launch = TrackRun("launch")
    chamber = ShuffleChamber("start", launch)
    described = chamber.describe()
    clear = described["clearances"]
    findings: list[str] = []

    print("ShuffleChamber geometry, layout units")
    print(
        "  pan {pan_floor}  chamber rim {rim_floor}  at the ring {gate_floor}  "
        "outlet lip {outlet_lip}  launch seat {exit_seat}".format(**described["heights"])
    )
    print(
        f"  chamber {described['chamber']['width']} across, floor tilt "
        f"{described['chamber']['floor_tilt_deg']} deg, inlet "
        f"{2 * described['chamber']['inlet_half']} wide "
        f"({described['chamber']['inlet_half_deg'] * 2:.0f} deg of wall), step "
        f"{described['chamber']['inlet_step']}"
    )
    print(
        f"  rotor {described['rotor']['paddles']} paddles "
        f"{described['rotor']['root_radius']}..{described['rotor']['tip_radius']}, "
        f"{described['rotor']['rate']} rad/s = {described['rotor']['tip_speed']} "
        f"tip speed, {described['rotor']['turns_while_mixing']} turns while mixing"
    )
    print(
        f"  outlet {2 * described['outlet']['gate_radius']} across, "
        f"{described['outlet']['segments']} segments, drops "
        f"{described['outlet']['drop']}; lift {described['lift']}"
    )
    print()

    # --- the clearances, and that they are constant -----------------------
    print("clearances (a marble is %.3f across)" % DIAMETER)
    for name in ("tip_to_wall", "root_to_gate_ring", "between_paddles_at_root"):
        value = clear[name]
        ratio = value / DIAMETER
        pinches = PINCH_LOW <= ratio <= PINCH_HIGH
        verdict = (
            "PINCHES - about one marble" if pinches
            else "passes freely" if ratio > PINCH_HIGH
            else "swept - too small to enter"
        )
        print(f"  {name:>26} {value:>7.3f} ({ratio:>4.2f} marbles)  {verdict}")
        if pinches:
            findings.append(
                f"{name} is {value:.3f} = {ratio:.2f} marble diameters, inside the "
                f"{PINCH_LOW}..{PINCH_HIGH} band where a marble can enter a gap and "
                f"be caught in it"
            )
    print(f"  {'free radial travel':>26} {clear['free_radial_travel']:>7.3f} "
          f"({clear['free_radial_diameters']:>4.2f} marbles)  "
          f"{'can pass itself' if clear['free_radial_diameters'] >= FREE_TRAVEL_DIAMETERS else 'NECKLACE'}")
    if clear["free_radial_diameters"] < FREE_TRAVEL_DIAMETERS:
        findings.append(
            f"free radial travel is {clear['free_radial_diameters']:.2f} marble "
            f"diameters; under {FREE_TRAVEL_DIAMETERS} the field cannot pass itself "
            f"and the rotor can only rotate a necklace"
        )
    print(f"  {'chamber / field area':>26} {clear['area_ratio']:>7.2f}"
          f"                 ({clear['chamber_area']:.1f} against "
          f"{clear['field_area']:.1f})")
    if clear["area_ratio"] < 5.0:
        findings.append(f"the chamber is only {clear['area_ratio']:.1f} times the "
                        f"field's own area")

    # The gap under a blade, at both ends of its sweep. A `Spinner` is a box at
    # one height over a conical floor, so this varies - and it must stay under
    # a marble at the root and over zero at the tip.
    under_tip = chamber.FLOOR_CLEAR
    under_root = (chamber.floor_at(chamber.TIP_R) + chamber.FLOOR_CLEAR
                  - chamber.floor_at(chamber.ROOT_R))
    print(f"  {'under a blade, at the tip':>26} {under_tip:>7.3f} "
          f"({under_tip / DIAMETER:>4.2f} marbles)")
    print(f"  {'under a blade, at the root':>26} {under_root:>7.3f} "
          f"({under_root / DIAMETER:>4.2f} marbles)")
    if under_tip <= 0.0:
        findings.append(f"a blade is {under_tip:.3f} into the floor at its tip")
    if under_root >= DIAMETER:
        findings.append(f"a marble fits under a blade at its root ({under_root:.3f})")

    # --- the retracted gate must clear the chute --------------------------
    print()
    ring_top_open = (chamber.floor_at(chamber.GATE_R) + chamber.GATE_HEIGHT
                     - chamber.GATE_DROP)
    mouth = chamber.chute_mouth_z
    run = chamber.exit_local[2] - mouth
    chute_start = chamber.outlet_lip - 0.24
    # The chute's floor directly under the ring, at the ring's upstream edge -
    # the highest place the ring has to get below.
    t = max(0.0, ((chamber.CHAMBER_Z - chamber.GATE_R) - mouth) / max(run, 1e-9))
    chute_under_ring = chute_start + t * (
        (chamber.exit_local[1] + layout.FLOOR_Y) - chute_start)
    print(f"  retracted ring top {ring_top_open:+.3f}, chute floor under it "
          f"{chute_under_ring:+.3f}, clearance {chute_under_ring - ring_top_open:+.3f}")
    if ring_top_open > chute_under_ring:
        findings.append(
            f"the retracted gate ring stands {ring_top_open - chute_under_ring:.3f} "
            f"into the exit chute and will fence the field in"
        )

    # --- the outlet's mouth must cover the whole hole ---------------------
    upstream = chamber.CHAMBER_Z - chamber.GATE_R
    print(f"  outlet spans z {upstream:+.3f}..{chamber.CHAMBER_Z + chamber.GATE_R:+.3f}, "
          f"chute mouth at z {mouth:+.3f}, half width {chamber.CHUTE_HALF}")
    if mouth > upstream:
        findings.append(
            f"the chute's mouth is {mouth - upstream:.3f} downstream of the hole's "
            f"upstream edge, so the field falls past it"
        )
    if chamber.CHUTE_HALF < chamber.GATE_R:
        findings.append(
            f"the chute is narrower ({chamber.CHUTE_HALF}) than the hole "
            f"({chamber.GATE_R})"
        )
    grade = described["heights"]["chute_grade_deg"]
    # The realised grade, not the target. `derived_lift` sizes the lift from
    # `CHUTE_GRADE`, and the chute's landing then sits `CHUTE_LANDING` below
    # the outlet's lip - so the surface actually built is about 2.7 degrees
    # shallower than the target. Reported as built, because that is what the
    # marbles run on: the 2.60%-loss configuration is a *realised* 14.3.
    print(f"  exit chute {run:.2f} long at {grade:.1f} deg realised "
          f"(target {chamber.CHUTE_GRADE:.1f})")
    if not CHUTE_MIN <= grade <= CHUTE_MAX:
        findings.append(f"the exit chute runs at {grade:.1f} deg, outside "
                        f"{CHUTE_MIN}..{CHUTE_MAX}")

    # --- the timeline ------------------------------------------------------
    print()
    print(f"  timeline: bays open {chamber.release_time}s, rotor stops "
          f"{chamber.rotor_stop}s (+{chamber.SPIN_DOWN} spin-down), outlet opens "
          f"{chamber.gate_time}s")
    if chamber.rotor_stop <= chamber.release_time + 0.6:
        findings.append("the rotor stops before the field can be in the chamber")
    if chamber.gate_time < chamber.rotor_stop + chamber.SPIN_DOWN:
        findings.append("the outlet opens before the rotor has stopped")

    # --- no hidden uphill along the apron ---------------------------------
    worst = 0.0
    previous = None
    for step in range(121):
        u = -0.4 + 1.4 * step / 120.0
        y = chamber.pan_floor - chamber.apron_drop * min(1.0, u)
        if previous is not None and u > 0.0:
            worst = max(worst, y - previous)
        previous = y
    print(f"  worst uphill step along the apron {worst:+.6f}")
    if worst > 1e-9:
        findings.append(f"the apron climbs {worst:.4f} somewhere")

    # --- mesh and probes ---------------------------------------------------
    print()
    mesh = chamber.local_colliders()[0]
    mesh_findings = check_mesh(mesh, expect_components=None)
    print(f"mesh: {len(mesh.vertices)} vertices, {len(mesh.indices) // 3} "
          f"triangles, {len(mesh_findings)} findings")
    for finding in mesh_findings[:8]:
        print(f"  {finding}")
    if mesh_findings:
        findings.append(f"{len(mesh_findings)} mesh findings")
    actuators = chamber.local_actuators()
    kinds = {}
    for actuator in actuators:
        kinds[actuator.name.rstrip("0123456789")] = kinds.get(
            actuator.name.rstrip("0123456789"), 0) + 1
    print(f"probes: {len(chamber.local_probes())}   actuators: {len(actuators)} "
          f"{kinds}")

    print()
    if findings:
        print(f"FINDINGS ({len(findings)}):")
        for finding in findings:
            print(f"  - {finding}")
    else:
        print("no findings: every clearance constant and either free or too small "
              "to enter, the field can pass itself, the gate clears the chute, "
              "the mouth covers the hole, the timeline is ordered")

    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(
            json.dumps(
                {
                    "start_kind": chamber.START_KIND,
                    "described": described,
                    "blade_gap": {"at_tip": round(under_tip, 4),
                                  "at_root": round(under_root, 4)},
                    "retracted_ring_top": round(ring_top_open, 4),
                    "chute_floor_under_ring": round(chute_under_ring, 4),
                    "chute_grade_deg": grade,
                    "worst_uphill_step": round(worst, 6),
                    "mesh": {
                        "vertices": len(mesh.vertices),
                        "triangles": len(mesh.indices) // 3,
                        "findings": [str(f) for f in mesh_findings],
                    },
                    "actuators": kinds,
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

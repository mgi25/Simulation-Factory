"""Validate the full-floor release's geometry before any marble is run.

    python tools/sloped_floor_check.py
    python tools/sloped_floor_check.py --json out.json

Section 6 of the V1.8 brief asks for the trapdoor's clearances to be validated
**throughout the complete floor-opening motion**, and says why: the earlier
wheel's jam was arithmetic nobody had done - a tip-to-wall gap that passed
through exactly one marble diameter four times a revolution. So this does not
check the resting geometry and trust a formula. It walks the sweep degree by
degree and measures the real box corners.

What it checks:

* **coverage.** The union of the slats covers the whole chamber disc at rest,
  sampled on a grid. A slat that falls short of the chord over part of its own
  band leaves a crescent at floor level with nothing under it.
* **the seams, through the sweep.** For every adjacent pair, at every degree,
  the horizontal gap between them. It must start closed, open monotonically,
  and finish over 1.25 marble diameters - and it must never *narrow*, which is
  the one property that makes a moving gap safe.
* **panel to wall.** No crescent between a slat's end and the chamber wall
  anywhere on the slat's own band, at any angle.
* **no sphere trapped against the wall.** For a marble resting against the
  chamber wall, the space it occupies must be clear of every slat by the time
  the slat could reach it, and the slat must move *away* from the wall.
* **hinge sweep against a marble on the dish.** Not against the dish surface:
  at 90 degrees the slats hang as vertical plates in the space above the dish,
  and a marble resting on it stands 0.57 tall into that space. The first
  version of this check asked for the clearance to the *surface*, reported a
  healthy +0.159, and six of fifteen stage-A traces landed cleanly and then
  rolled along a slat's face for the rest of the run.
* **the dish catches everything.** Every point of the chamber disc must be over
  the dish, or a marble falls out of the machine - which V1.5's chute did, and
  reported nothing, because a marble that never touches a run is never located
  on one.
* **the fall.** How far a marble drops from the chamber floor to the dish, over
  the whole chamber, and the impact speed that implies at layout gravity.
* **the release reads nothing.** Every panel is given one release time and one
  duration, and they are all the same.
* the timeline, the mesh and the probes, as every other module answers.
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
from sloped.scale import SIM_TO_LAYOUT  # noqa: E402
from sloped.shuffle import chamber_table  # noqa: E402
from sloped.trapdoor import (  # noqa: E402
    ShuffleFloor,
    floor_table,
    panels_by_index,
    seam_gap,
)
from sloped.track import TrackRun  # noqa: E402

DIAMETER = 2.0 * layout.MARBLE_RADIUS
# The band in which a gap is dangerous, as a fraction of a marble. Copied from
# `tools/sloped_rotor_check.py` deliberately: below 0.45 of a diameter a marble
# cannot enter a gap at all and the surface sweeps it, above 1.25 it passes
# through with room, and between the two it can get in and be held.
PINCH_LOW = 0.45
PINCH_HIGH = 1.25
# Layout-scale gravity, for reporting a fall as a speed. See `sloped.scale`:
# the core simulates at 245.25 world units per second squared and the layout is
# 0.57 of that scale.
GRAVITY = 245.25 * SIM_TO_LAYOUT
SWEEP_ROUNDING = 1.0             # degrees between samples of the sweep


def _sweep_angles(floor):
    """Every degree of the sweep, whatever the sweep happens to be."""
    steps = int(round(floor.PANEL_SWEEP / SWEEP_ROUNDING))
    return [
        math.radians(floor.PANEL_SWEEP * step / steps) for step in range(steps + 1)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None)
    options = parser.parse_args(argv)

    launch = TrackRun("launch")
    floor = ShuffleFloor("start", launch)
    described = floor.describe()
    findings: list[str] = []
    report: dict = {"start_kind": floor.START_KIND, "described": described}

    print("ShuffleFloor geometry, layout units")
    heights = described["heights"]
    print(
        "  pan {pan_floor}  chamber floor {chamber_floor}  dish rim {dish_edge}  "
        "dish lip {dish_lip}  launch seat {exit_seat}".format(**heights)
    )
    print(
        f"  chamber {described['chamber']['width']} across, floor tilt "
        f"{described['chamber']['floor_tilt_deg']} deg (flat), inlet "
        f"{2 * described['chamber']['inlet_half']} wide, step "
        f"{described['chamber']['inlet_step']}"
    )
    rotor = described["rotor"]
    print(
        f"  rotor {rotor['paddles']} paddles {rotor['root_radius']}.."
        f"{rotor['tip_radius']}, {rotor['rate']} rad/s, held for entry "
        f"{rotor['holds_until_field_in']}, turns {rotor['starts_at']}.."
        f"{rotor['stops_at']}s = {rotor['turns_while_mixing']} revolutions"
    )
    table = floor_table(floor)["floor"]
    print(
        f"  louvre {table['panels']} slats at pitch {table['pitch']} "
        f"({table['pitch_diameters']} marbles), {table['boxes']} boxes, sweeping "
        f"{table['sweep_deg']} deg in {table['duration']}s from {table['opens_at']}s"
    )
    print(
        f"  seam reaches one marble at {table['seam_passes_a_marble_at_deg']} deg "
        f"and passes freely at {table['seam_passes_freely_at_deg']} deg; finishes "
        f"{table['final_seam']} ({table['final_seam_diameters']} marbles)"
    )
    catch = described["catch"]
    print(
        f"  dish {catch['width']} across, back {catch['back_z']} to spillway "
        f"{catch['spill_z']}, depth {catch['dish_depth']} = {catch['slope_deg']} "
        f"deg, rim {catch['rim_rise']}; lift {described['lift']}"
    )
    print(f"  chute {heights['chute_run']} long at {heights['chute_grade_deg']} deg")
    print()

    # --- the release reads nothing ----------------------------------------
    panels = floor.floor_panels()
    times = {(p.release_time, p.duration, p.sweep) for p in panels}
    print(f"position independence: {len(panels)} panels, "
          f"{len(times)} distinct (release, duration, sweep) triple(s)")
    if len(times) != 1:
        findings.append(
            f"the panels do not share one release: {sorted(times)} - the timing "
            f"has to depend on the tick and the configuration and nothing else"
        )
    report["release_triples"] = sorted(
        [round(t[0], 6), round(t[1], 6), round(t[2], 6)] for t in times
    )

    # --- coverage of the chamber disc at rest ------------------------------
    print()
    worst_uncovered = None
    samples = 0
    for row in range(-40, 41):
        for column in range(-40, 41):
            x = column * floor.R_WALL / 40.0
            z = row * floor.R_WALL / 40.0
            if math.hypot(x, z) > floor.R_WALL:
                continue
            samples += 1
            index = int(math.floor((z + floor.R_WALL) / floor.panel_pitch))
            index = min(max(index, 0), floor.PANELS - 1)
            low, high = floor.panel_band(index)
            if not (low - 1e-9 <= z <= high + 1e-9):
                worst_uncovered = ("band", x, z)
                continue
            step = floor.panel_pitch / floor.PANEL_SPLITS
            split = min(int(math.floor((z - low) / step)), floor.PANEL_SPLITS - 1)
            sub_low = low + split * step
            reach = floor.panel_half_length(sub_low, sub_low + step)
            if abs(x) > reach:
                short = abs(x) - reach
                if worst_uncovered is None or short > worst_uncovered[0]:
                    worst_uncovered = (short, x, z)
    print(f"coverage: {samples} points of the chamber disc sampled")
    if worst_uncovered is None:
        print("  every one of them is over a slat")
    else:
        findings.append(
            f"the slats do not cover the disc: {worst_uncovered[1]:.3f}, "
            f"{worst_uncovered[2]:.3f} is short by {worst_uncovered[0]}"
        )
    report["coverage_samples"] = samples
    report["coverage_gap"] = None if worst_uncovered is None else str(worst_uncovered)

    # --- the seams, through the whole sweep --------------------------------
    #
    # `along` is the direction the seam opens in: perpendicular to the hinge
    # and to world up, which for this module is its own +z.
    along = tuple(float(v) for v in floor.frame[2])
    by_panel = panels_by_index(floor)

    print()
    print("seams, every degree of the sweep (a marble is %.3f across)" % DIAMETER)
    angles = _sweep_angles(floor)
    seam_rows = []
    worst_narrowing = 0.0
    for index in range(floor.PANELS - 1):
        gaps = []
        for angle in angles:
            here = [c for p in by_panel[index] for c in p.corners_at(angle)]
            there = [c for p in by_panel[index + 1] for c in p.corners_at(angle)]
            gaps.append(seam_gap(here, there, along))
        narrowing = max(
            (gaps[step] - gaps[step + 1] for step in range(len(gaps) - 1)),
            default=0.0,
        )
        worst_narrowing = max(worst_narrowing, narrowing)
        seam_rows.append(
            {
                "seam": f"{index}|{index + 1}",
                "at_rest": round(gaps[0], 4),
                "at_90": round(gaps[min(len(gaps) - 1, int(90.0 / SWEEP_ROUNDING))], 4),
                "final": round(gaps[-1], 4),
                "final_diameters": round(gaps[-1] / DIAMETER, 3),
                "worst_narrowing": round(narrowing, 6),
            }
        )
    header = ("seam | at rest |   at 90 |   final | marbles | worst narrowing")
    print(f"  {header}")
    print("  " + "-" * len(header))
    for row in seam_rows:
        print(
            f"   {row['seam']} | {row['at_rest']:7.3f} | {row['at_90']:7.3f} | "
            f"{row['final']:7.3f} | "
            f"{row['final_diameters']:7.3f} | {row['worst_narrowing']:+.6f}"
        )
    print("  " + "-" * len(header))
    if worst_narrowing > 1e-6:
        findings.append(
            f"a seam narrows by {worst_narrowing:.4f} somewhere in the sweep; a "
            f"gap that closes is a scissor whatever its size"
        )
    else:
        print("  no seam narrows at any point of the sweep - every gap only opens")
    tightest_final = min(row["final_diameters"] for row in seam_rows)
    if tightest_final < PINCH_HIGH:
        findings.append(
            f"the tightest final seam is {tightest_final:.2f} marble diameters, "
            f"under the {PINCH_HIGH} a marble needs to pass freely"
        )
    report["seams"] = seam_rows
    report["worst_seam_narrowing"] = round(worst_narrowing, 6)

    # --- panel against the chamber wall -----------------------------------
    #
    # Two questions, and they are different. Is there a crescent at floor level
    # between a slat's end and the wall for a marble to sit in? And once the
    # slat moves, does it move *away* from the wall or into the space a marble
    # against the wall occupies?
    print()
    worst_crescent = 0.0
    worst_at = None
    for index in range(floor.PANELS):
        low, high = floor.panel_band(index)
        step = floor.panel_pitch / floor.PANEL_SPLITS
        for split in range(floor.PANEL_SPLITS):
            sub_low = low + split * step
            reach = floor.panel_half_length(sub_low, sub_low + step)
            for sample in range(9):
                z = sub_low + step * sample / 8.0
                chord = math.sqrt(max(floor.R_WALL ** 2 - z * z, 0.0))
                if chord - reach > worst_crescent:
                    worst_crescent = chord - reach
                    worst_at = (index, split, round(z, 3))
    ratio = worst_crescent / DIAMETER
    print(f"panel to wall: worst crescent {worst_crescent:+.4f} "
          f"({ratio:.3f} marbles)"
          + ("" if worst_at is None else f" at panel {worst_at[0]}.{worst_at[1]}, "
             f"z {worst_at[2]}"))
    if ratio >= PINCH_LOW:
        findings.append(
            f"a crescent {worst_crescent:.3f} deep ({ratio:.2f} marbles) stands "
            f"between a slat's end and the chamber wall; a marble can sit in it"
        )
    else:
        print("  every slat reaches its chord, so there is no gap against the wall")
    report["worst_wall_crescent"] = round(worst_crescent, 5)

    # A marble resting against the wall, at each panel's own band: does any
    # slat sweep into the sphere it occupies?
    # A marble resting against the chamber wall, on each slat's own band: once
    # its slat starts to move, does the slat push *into* the sphere? A slat
    # supporting a marble is exactly one radius away at rest, so what is
    # measured is whether that distance ever falls below it - a panel that
    # merely drops away is fine and a panel that swings into the marble is not.
    trapped = []
    encroach = {}
    for index in range(floor.PANELS):
        low, high = floor.panel_band(index)
        limit = floor.R_WALL - layout.MARBLE_RADIUS
        for lane in (0.25, 0.5, 0.75):
            centre_z = low + (high - low) * lane
            if abs(centre_z) >= limit:
                continue
            marble_x = math.sqrt(limit * limit - centre_z * centre_z)
            for side in (-1.0, 1.0):
                seat = floor.rim_floor + layout.MARBLE_RADIUS
                centre = _place_marble(floor, side * marble_x, seat, centre_z)
                for angle in angles[1:]:
                    near = min(
                        panel.distance_to(centre, angle) for panel in by_panel[index]
                    ) * SIM_TO_LAYOUT
                    short = layout.MARBLE_RADIUS - near
                    key = index
                    if short > encroach.get(key, -1e9):
                        encroach[key] = short
                    # A tenth of a radius of overlap is contact rather than
                    # rounding, and contact from a panel that is moving down
                    # and away is not a trap.
                    if short > 0.1 * layout.MARBLE_RADIUS:
                        trapped.append((index, round(math.degrees(angle), 1),
                                        round(short, 4)))
                        break
    worst_encroach = max(encroach.values()) if encroach else 0.0
    print(f"  a marble against the wall: {len(trapped)} panel-angle(s) push into "
          f"it; worst encroachment {worst_encroach:+.4f} of a "
          f"{layout.MARBLE_RADIUS} radius")
    if trapped:
        findings.append(
            f"panels {sorted({row[0] for row in trapped})} sweep into the space a "
            f"marble resting against the chamber wall occupies, by up to "
            f"{max(row[2] for row in trapped):.3f}"
        )
    report["wall_marble_conflicts"] = trapped
    report["worst_wall_encroachment"] = round(worst_encroach, 5)

    # --- the slats' depth against the dish --------------------------------
    #
    # **In the module's own frame, not the world's.** `_place` adds the
    # module's origin - which the derived lift has already moved - and then
    # converts to simulation units, so a world y compared against a local
    # `rim_floor` is out by the whole origin and reads zero depth for a panel
    # that swings a unit down. The first run of this check did exactly that.
    print()
    floor_world_y = _place_marble(floor, 0.0, floor.rim_floor, 0.0)[1]
    deepest = 0.0
    deepest_angle = 0.0
    for panel in panels:
        for angle in angles:
            for corner in panel.corners_at(angle):
                depth = (floor_world_y - corner[1]) * SIM_TO_LAYOUT
                if depth > deepest:
                    deepest, deepest_angle = depth, math.degrees(angle)
    # **Against the top of a marble on the dish, not against the dish.** See
    # the module header: the slats hang rather than going away, and a marble
    # standing on the dish reaches 0.57 up into the space they hang in.
    marble_top = floor.panel_well - DIAMETER
    clearance = marble_top - deepest
    print(f"slat sweep: deepest {deepest:.4f} below the chamber floor (at "
          f"{deepest_angle:.0f} deg); the dish rim is {floor.panel_well:.4f} down "
          f"and a marble on it reaches {marble_top:.4f}, clearance "
          f"{clearance:+.4f}")
    if clearance <= 0.0:
        findings.append(
            f"a marble resting on the dish stands {-clearance:.3f} into the "
            f"slats' hanging position; it will roll along a slat's face instead "
            f"of down the dish"
        )
    report["deepest_sweep"] = round(deepest, 5)
    report["deepest_sweep_deg"] = round(deepest_angle, 2)
    report["panel_well"] = round(floor.panel_well, 5)
    report["marble_top_on_dish"] = round(marble_top, 5)
    report["dish_clearance"] = round(clearance, 5)

    # --- the dish catches the whole chamber -------------------------------
    outside = 0
    for row in range(-30, 31):
        for column in range(-30, 31):
            x = column * floor.R_WALL / 30.0
            z = row * floor.R_WALL / 30.0
            if math.hypot(x, z) > floor.R_WALL:
                continue
            if not floor._inside(x, floor.CHAMBER_Z + z):
                outside += 1
    print(f"dish coverage: {outside} point(s) of the chamber disc are not over "
          f"the dish")
    if outside:
        findings.append(
            f"{outside} points of the chamber floor are not over the dish; a "
            f"marble there falls out of the machine"
        )
    report["chamber_points_off_dish"] = outside

    # --- the fall ---------------------------------------------------------
    print()
    falls = []
    for row in range(-24, 25):
        for column in range(-24, 25):
            x = column * floor.R_WALL / 24.0
            z = row * floor.R_WALL / 24.0
            if math.hypot(x, z) > floor.R_WALL - layout.MARBLE_RADIUS:
                continue
            falls.append(floor.fall_to_dish(x, floor.CHAMBER_Z + z))
    low, high = min(falls), max(falls)
    mean = sum(falls) / len(falls)
    def speed(fall):
        return math.sqrt(max(2.0 * GRAVITY * fall, 0.0))
    print(f"the fall onto the dish: {low:.3f} to {high:.3f}, mean {mean:.3f}")
    print(f"  landing speed {speed(low):.1f} to {speed(high):.1f} layout units "
          f"per second at g = {GRAVITY:.1f}")
    print(f"  rebound at restitution 0.15 rises "
          f"{0.7 * (0.15 * speed(high)) ** 2 / GRAVITY:.3f}, against a "
          f"{floor.DISH_RIM_RISE} rim")
    report["fall"] = {
        "min": round(low, 4), "max": round(high, 4), "mean": round(mean, 4),
        "speed_min": round(speed(low), 3), "speed_max": round(speed(high), 3),
        "gravity": round(GRAVITY, 3),
    }
    if 0.7 * (0.15 * speed(high)) ** 2 / GRAVITY > floor.DISH_RIM_RISE:
        findings.append("a marble could rebound over the dish's rim")

    # --- the rotor's clearances, which are now constant everywhere --------
    print()
    clear = chamber_table(floor)["clearances"]
    # `root_to_gate_ring` is skipped rather than printed: there is no ring, so
    # the parent table's figure is just the root radius and calling it a
    # clearance would be a number that means nothing in this chamber.
    for name in ("tip_to_wall", "between_paddles_at_root"):
        value = clear[name]
        ratio = value / DIAMETER
        pinches = PINCH_LOW <= ratio <= PINCH_HIGH
        print(f"  {name:>26} {value:>7.3f} ({ratio:>4.2f} marbles)"
              f"{'  PINCHES' if pinches else ''}")
        if pinches:
            findings.append(f"{name} is {ratio:.2f} marble diameters")
    under = floor.FLOOR_CLEAR
    print(f"  {'under a blade, everywhere':>26} {under:>7.3f} "
          f"({under / DIAMETER:>4.2f} marbles)  the floor is level, so this is "
          f"one number")
    free = clear["free_radial_travel"]
    print(f"  {'free radial travel':>26} {free:>7.3f} "
          f"({clear['free_radial_diameters']:>4.2f} marbles)  the whole disc")
    print(f"  {'open centre, no blade':>26} {floor.ROOT_R:>7.3f} "
          f"({floor.ROOT_R / DIAMETER:>4.2f} marbles)  and no ring in it")
    report["clearances"] = clear

    # --- the timeline -----------------------------------------------------
    print()
    print(f"  timeline: bays open {floor.release_time}s, rotor turns "
          f"{floor.rotor_start}..{floor.rotor_stop}s (+{floor.SPIN_DOWN} "
          f"spin-down), floor opens {floor.floor_open}s over "
          f"{floor.FLOOR_DURATION}s")
    if floor.rotor_start < floor.release_time:
        findings.append("the rotor starts before the bays open")
    if floor.rotor_stop <= floor.rotor_start:
        findings.append("the rotor stops before it starts")
    if floor.floor_open < floor.rotor_stop + floor.SPIN_DOWN:
        findings.append("the floor opens before the rotor has stopped")

    # --- the paddles are clear of a marble before the floor opens ---------
    raised = floor.ROTOR_LIFT
    blade_under = floor.rim_floor + floor.FLOOR_CLEAR + raised
    marble_top = floor.rim_floor + DIAMETER
    print(f"  the paddles rise {raised} from {floor.rotor_lift_time:.3f}s over "
          f"{floor.ROTOR_LIFT_OVER}s, putting a blade's underside "
          f"{blade_under - floor.rim_floor:+.3f} above the floor against a "
          f"marble's {DIAMETER:.3f}")
    if blade_under < marble_top:
        findings.append(
            f"a raised blade's underside is still {marble_top - blade_under:.3f} "
            f"inside a marble standing on the chamber floor, so it can be the "
            f"third wall of a pocket"
        )
    if floor.rotor_lift_time + floor.ROTOR_LIFT_OVER > floor.floor_open:
        findings.append("the paddles are still rising when the floor opens")
    if floor.rotor_lift_time < floor.rotor_stop + floor.SPIN_DOWN:
        findings.append("the paddles start rising before the rotor has stopped")
    report["rotor_lift"] = {
        "by": raised,
        "at": round(floor.rotor_lift_time, 4),
        "over": floor.ROTOR_LIFT_OVER,
        "blade_clearance": round(blade_under - marble_top, 4),
    }

    # --- mesh and probes ---------------------------------------------------
    print()
    mesh = floor.local_colliders()[0]
    mesh_findings = check_mesh(mesh, expect_components=None)
    print(f"mesh: {len(mesh.vertices)} vertices, {len(mesh.indices) // 3} "
          f"triangles, {len(mesh_findings)} findings")
    for finding in mesh_findings[:8]:
        print(f"  {finding}")
    if mesh_findings:
        findings.append(f"{len(mesh_findings)} mesh findings")
    actuators = floor.local_actuators()
    kinds: dict[str, int] = {}
    for actuator in actuators:
        key = actuator.name.rstrip("0123456789_")
        kinds[key] = kinds.get(key, 0) + 1
    print(f"probes: {len(floor.local_probes())}   actuators: {len(actuators)} {kinds}")
    report["mesh"] = {
        "vertices": len(mesh.vertices),
        "triangles": len(mesh.indices) // 3,
        "findings": [str(f) for f in mesh_findings],
    }
    report["actuators"] = kinds

    print()
    if findings:
        print(f"FINDINGS ({len(findings)}):")
        for finding in findings:
            print(f"  - {finding}")
    else:
        print("no findings: the slats cover the disc, no seam narrows at any "
              "angle of the sweep, every seam finishes over 1.25 marbles, no "
              "slat leaves a crescent against the wall or sweeps into a marble "
              "resting on it, the slats clear the dish, the dish catches the "
              "whole chamber, and one release time is shared by all of them")

    report["findings"] = findings
    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {options.json}")
    return 1 if findings else 0


def _place_marble(floor, x: float, y: float, z: float):
    """A marble centre in the chamber, as a world simulation point."""
    from sloped.stations import _place

    return _place(floor.origin, floor.frame, (x, y, floor.CHAMBER_Z + z))


if __name__ == "__main__":
    raise SystemExit(main())

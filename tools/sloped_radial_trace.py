"""Trace the radial start in simulation: where the field gets to, and when.

    python tools/sloped_radial_trace.py --seeds 3
    python tools/sloped_radial_trace.py --seeds 1 --bays 3 --hold 9
    python tools/sloped_radial_trace.py --seeds 20 --json out.json

Section 9 of the V1.4 brief asks for a validation order - geometry, then one
marble from every bay, then a synchronised eight, then a few dozen seeds - and
this is the instrument for the middle three. It runs the start module *alone*,
without the launch or leg1, and reports the two things the fairness argument
needs to be true and the one thing throughput needs:

* **arrival**: did the marble reach the trough, and at what time;
* **rest**: what radius from the drain and what height it settled at, and how
  far those spread across the eight - the invariants the architecture exists to
  establish, measured rather than assumed;
* **release**: where it was `after` seconds past the ring's lift, which is what
  says whether the drain passes a field or arches over it.

`--bays` runs a single marble from one bay with the ring held shut, which is
step B of the order and the cheapest way to see a guide fail.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marble3d.config import DEFAULT_CONFIG  # noqa: E402
from marble3d.geometry import Transform  # noqa: E402
from marble3d.machine import Machine  # noqa: E402
from marble3d.simulation import MarbleSimulation  # noqa: E402
from sloped import layout  # noqa: E402
from sloped.radial import RadialStart  # noqa: E402
from sloped.scale import SIM_TO_LAYOUT, to_sim  # noqa: E402
from sloped.track import TrackRun  # noqa: E402

# A marble is "in the trough" once it is inside the rim and within a marble of
# the trough's floor. Both in layout units, in the module's own frame.
RIM_SLACK = 0.20
FLOOR_SLACK = 0.50


def build(port_gate: bool = True, bays=None, hold: float = 0.0
          ) -> tuple[Machine, RadialStart]:
    launch = TrackRun("launch")
    start = RadialStart("start", launch, port_gate=port_gate)
    if hold:
        # On the instance, so that `local_actuators` builds the gates with it.
        # Mutating the gates returned by a *separate* call changes nothing the
        # simulation ever sees, which is what the first version did.
        start.RELEASE = hold
    if bays is not None:
        keep = list(bays)
        original = start.marble_starts

        def only_these():
            return [original()[i] for i in keep]

        start.marble_starts = only_these        # type: ignore[method-assign]
    machine = Machine("radial_trace")
    machine.add(start, Transform())
    return machine, start


def local_of(start: RadialStart, world) -> tuple[float, float, float]:
    """A simulation-unit world point back in the module's own layout frame."""
    layout_point = [value * SIM_TO_LAYOUT for value in world]
    delta = [layout_point[axis] - start.origin[axis] for axis in range(3)]
    ax, ay, az = start.frame
    return (
        sum(delta[axis] * ax[axis] for axis in range(3)),
        sum(delta[axis] * ay[axis] for axis in range(3)),
        sum(delta[axis] * az[axis] for axis in range(3)),
    )


def run(seed: int, bays=None, hold: float = 0.0, after: float = 1.4,
        port_gate: bool = True, duration: float = 14.0) -> dict:
    machine, start = build(port_gate=port_gate, bays=bays, hold=hold)
    release = max(
        (g.release_time + g.duration for g in machine.modules["start"].local_actuators()
         if g.name.startswith("port")),
        default=0.0,
    )
    count = len(start.marble_starts())
    sim = MarbleSimulation(machine, DEFAULT_CONFIG, seed, count)
    hz = DEFAULT_CONFIG.physics.physics_hz
    rim = start.TROUGH_R + start.TROUGH_HALF
    rows = {
        mid: {
            "bay": (bays[m.start_index] if bays else m.start_index),
            "arrived": None, "rest_radius": None, "rest_y": None,
            "after_radius": None, "after_y": None, "min_radius": None,
            "escaped": None, "max_drop": 0.0, "seated": None,
            "rest_bearing": None, "bearing_drift": None,
        }
        for mid, m in sim.marbles.items()
    }
    try:
        limit = int(round(duration * hz))
        while sim.ticks < limit:
            sim.step()
            if sim.ticks % 8:
                continue
            now = sim.ticks / hz
            for mid, marble in sim.marbles.items():
                row = rows[mid]
                x, y, z = local_of(start, marble.pose[0])
                radius = math.hypot(x, z - start.DISH_Z)
                row["min_radius"] = (radius if row["min_radius"] is None
                                     else min(row["min_radius"], radius))
                row["max_drop"] = max(row["max_drop"], start.rest_floor - y)
                if row["escaped"] is None and y < start.drain_lip - 3.0:
                    row["escaped"] = round(now, 3)
                if row["arrived"] is None and radius < rim + RIM_SLACK:
                    if abs(y - start.trough_y(max(radius, start.DRAIN_R))) < FLOOR_SLACK:
                        row["arrived"] = round(now, 3)
                # Seated: against the ring, on its floor, and stopped. This
                # is what `RELEASE` has to wait for, and it is longer than
                # arrival - a marble reaches the trough and then has to find a
                # bearing of its own among seven others.
                if abs(radius - start.rest_radius) < 0.12 and math.hypot(
                        *marble.pose[2]) * SIM_TO_LAYOUT < 0.6:
                    if row["seated"] is None:
                        row["seated"] = round(now, 3)
                elif now <= release:
                    row["seated"] = None
                if row["arrived"] is not None and now <= release + 1e-6:
                    row["rest_radius"] = round(radius, 4)
                    row["rest_y"] = round(y, 4)
                    # Bearing round the ring, and how far it has drifted from
                    # the bearing this bay's guide delivers at. This is the one
                    # coordinate the trough does *not* equalise, and whether it
                    # stays tied to the bay decides whether the architecture
                    # can be fair at all.
                    bearing = math.degrees(math.atan2(z - start.DISH_Z, x)) % 360.0
                    row["rest_bearing"] = round(bearing, 2)
                    want = start.guides().bearing(row["bay"])
                    row["bearing_drift"] = round(
                        (bearing - want + 180.0) % 360.0 - 180.0, 2)
                if abs(now - (release + after)) < 1.0 / hz * 8.5:
                    row["after_radius"] = round(radius, 4)
                    row["after_y"] = round(y, 4)
    finally:
        sim.close()

    arrived = [r for r in rows.values() if r["arrived"] is not None]
    seated = max((r["seated"] for r in rows.values() if r["seated"] is not None),
                 default=None) if all(r["seated"] is not None for r in rows.values()
                                      ) else None
    radii = [r["rest_radius"] for r in rows.values() if r["rest_radius"] is not None]
    heights = [r["rest_y"] for r in rows.values() if r["rest_y"] is not None]
    return {
        "seed": seed,
        "release": round(release, 3),
        "racers": len(rows),
        "arrived": len(arrived),
        "arrival": [round(min(r["arrived"] for r in arrived), 3),
                    round(max(r["arrived"] for r in arrived), 3)] if arrived else None,
        "rest_radius_spread": round(max(radii) - min(radii), 4) if len(radii) > 1 else None,
        "rest_radius": [round(min(radii), 4), round(max(radii), 4)] if radii else None,
        "rest_y_spread": round(max(heights) - min(heights), 4) if len(heights) > 1 else None,
        "seated": seated,
        "rows": sorted(rows.values(), key=lambda r: r["bay"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--bays", type=int, nargs="*", default=None)
    parser.add_argument("--hold", type=float, default=0.0,
                        help="override the ring's release time, in seconds")
    parser.add_argument("--after", type=float, default=1.4)
    parser.add_argument("--duration", type=float, default=14.0)
    parser.add_argument("--no-gate", action="store_true")
    parser.add_argument("--json", type=Path, default=None)
    options = parser.parse_args(argv)

    results = []
    for seed in range(options.first, options.first + options.seeds):
        result = run(seed, bays=options.bays, hold=options.hold,
                     after=options.after, port_gate=not options.no_gate,
                     duration=options.duration)
        results.append(result)
        head = (
            f"seed {seed}: {result['arrived']}/{result['racers']} reached the trough"
        )
        if result["seated"] is not None:
            head += f", all seated by {result['seated']:.2f}s"
        else:
            head += ", NOT all seated"
        if result["arrival"]:
            head += f", arriving {result['arrival'][0]:.2f}..{result['arrival'][1]:.2f}s"
        print(head)
        print(
            f"{'bay':>3} {'arrive':>7} {'restR':>7} {'restY':>8} "
            f"{'restBrg':>8} {'drift':>7} {'minR':>6} "
            f"{'drop':>6} {'afterR':>7} {'afterY':>8} {'escaped':>8}"
        )
        for row in result["rows"]:
            def show(value, fmt="7.3f"):
                return format(value, fmt) if value is not None else "      -"
            print(
                f"{row['bay']:>3} {show(row['arrived'])} {show(row['rest_radius'])} "
                f"{show(row['rest_y'], '8.3f')} {show(row['rest_bearing'], '8.2f')} "
                f"{show(row['bearing_drift'], '7.2f')} "
                f"{show(row['min_radius'], '6.2f')} "
                f"{show(row['max_drop'], '6.2f')} {show(row['after_radius'])} "
                f"{show(row['after_y'], '8.3f')} {show(row['escaped'], '8.2f')}"
            )
        drifts = [abs(r["bearing_drift"]) for r in result["rows"]
                  if r["bearing_drift"] is not None]
        if drifts:
            print(f"  bearing drift from the delivery bearing: "
                  f"{min(drifts):.1f}..{max(drifts):.1f} deg, mean "
                  f"{sum(drifts) / len(drifts):.1f}")
        if result["rest_radius_spread"] is not None:
            print(
                f"  resting radius {result['rest_radius'][0]:.3f}.."
                f"{result['rest_radius'][1]:.3f}, spread "
                f"{result['rest_radius_spread']:.4f}; height spread "
                f"{result['rest_y_spread']:.4f}"
            )
        print()

    total = sum(r["racers"] for r in results)
    through = sum(r["arrived"] for r in results)
    print(f"TOTAL {through}/{total} = {100.0 * through / max(total, 1):.1f}% reached the trough")
    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {options.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

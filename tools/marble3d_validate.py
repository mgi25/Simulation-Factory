"""The production-hardening battery, run as one command.

    python -m tools.marble3d_validate --all

Every section here corresponds to a category section 27 of the brief asks for a
regression around, and every number in `docs/marble3d_physics_core.md` comes
out of this tool rather than being typed. Run it with `--report` to write the
JSON the document quotes.

The determinism section is the one worth reading the code of: `--determinism`
launches child interpreters through `tools.marble3d_run --digest-only`, because
a same-process repeat shares an allocator, a geometry cache and a warm heap
with its predecessor and cannot see the failure that actually happens - which
is Bullet's broadphase pair ordering depending on allocation addresses.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from typing import Any

from marble3d.config import DEFAULT_CONFIG
from marble3d.experiments import (
    measure_contact_separation,
    measure_incline,
    measure_resting_height,
    measure_rolling_resistance,
    measure_throughput,
    measure_tunnelling,
)
from marble3d.machines import start_bowl_curve
from marble3d.metrics import entry_speeds, revolutions, summarise
from marble3d.modules.start import StartSpec
from marble3d.simulation import environment_metadata, simulate
from marble3d.units import GRAVITY, MARBLE_DIAMETER, MARBLE_RADIUS, describe
from marble3d.validation import check_machine

DEFAULT_REPORT = os.path.join("docs", "validation", "marble3d", "hardening.json")
SEEDS = (7, 11, 19, 23, 31, 42, 57, 68)


def _header(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


# --- sections -------------------------------------------------------------


def section_colliders() -> dict[str, Any]:
    _header("Collider integrity")
    findings, facts = check_machine(start_bowl_curve())
    print(f"  {facts['colliders']} collision bodies, {facts['triangles']} triangles, "
          f"{facts['vertices']} vertices")
    print(f"  {facts['probes']} ray probes fired against the assembled world")
    for finding in findings:
        print(f"  FAIL {finding}")
    if not findings:
        print("  all clear: no holes, no phantom geometry, no surface out of place")
    return {"facts": facts, "findings": [f.__dict__ for f in findings]}


def section_margins() -> dict[str, Any]:
    _header("Collision margins")
    rows = []
    for margin in (0.04, 0.01, 0.001, 0.0001):
        error = measure_resting_height(margin=margin)
        rows.append({"margin": margin, "resting_height_error": error})
        print(f"  mesh margin {margin:<8} resting height error {error:+.6f} wu "
              f"({100 * error / MARBLE_RADIUS:+.4f}% of a marble radius)")
    touch, clear = measure_contact_separation()
    diameter = DEFAULT_CONFIG.marble.diameter
    print(f"  two marbles touch at <= {touch:.4f} and are clear at >= {clear:.4f}; "
          f"a diameter is {diameter:.4f}")
    crr = measure_rolling_resistance()
    print(f"  rolling-resistance floor of the tessellated collider: Crr = {crr:.5f}")
    return {
        "resting_height": rows,
        "contact_touch": touch,
        "contact_clear": clear,
        "diameter": diameter,
        "tessellation_crr": crr,
    }


def section_friction() -> dict[str, Any]:
    _header("Friction: measured, not configured")
    rows = []
    steepest = math.degrees(start_bowl_curve().modules["bowl"].spec.steepest_angle())
    for slope in (10.0, 20.0, 30.0, steepest):
        result = measure_incline(slope)
        rows.append(result.to_json())
        verdict = "rolls" if result.rolls else "SKIDS"
        print(f"  {slope:>5.1f} deg  measured {result.measured_acceleration:8.2f}  "
              f"(5/7)g sin = {result.rolling_prediction:8.2f}  "
              f"needs mu >= {result.threshold_friction:.3f}  {verdict}")
    # And the negative control: below the threshold it has to skid, or the
    # measurement is not measuring anything.
    starved = measure_incline(30.0, surface_friction=0.10)
    rows.append({"starved": starved.to_json()})
    print(f"  30.0 deg at mu = 0.10 (below the {starved.threshold_friction:.3f} threshold): measured "
          f"{starved.measured_acceleration:.2f}, sliding law predicts "
          f"{starved.sliding_prediction:.2f}, recovered mu = {starved.inferred_friction:.3f}")
    return {"inclines": rows}


def section_rates() -> dict[str, Any]:
    _header("Physics rate")
    rows = []
    for hz in (120, 240, 480):
        config = DEFAULT_CONFIG.with_overrides(physics__physics_hz=hz)
        started = time.perf_counter()
        replay = simulate(seed=7, machine=start_bowl_curve(), config=config)
        wall = time.perf_counter() - started
        summary = summarise(replay)
        travel = summary["top_speed"] / hz
        rows.append(
            {
                "hz": hz,
                "top_speed": summary["top_speed"],
                "travel_per_tick": travel,
                "travel_in_diameters": travel / MARBLE_DIAMETER,
                "worst_penetration": summary["worst_penetration"],
                "finished": summary["finished"],
                "escaped": summary["escaped"],
                "sim_seconds": summary["sim_seconds"],
                "wall_seconds": wall,
                "revolutions_median": summary["revolutions_median"],
                "max_energy_rise": summary["max_energy_rise"],
            }
        )
        print(f"  {hz:>4} Hz  travel/tick {travel:.4f} wu "
              f"({travel / MARBLE_DIAMETER:.2f} diameters)  "
              f"worst penetration {summary['worst_penetration']:+.4f}  "
              f"turns {summary['revolutions_median']:.2f}  "
              f"{summary['finished']}/8 finished  wall {wall:.2f}s")
    _header("Tunnelling, by travel per tick")
    tunnel = []
    for speed in (60.0, 100.0, 150.0, 200.0, 300.0, 400.0):
        travel = speed / DEFAULT_CONFIG.physics.physics_hz
        with_ccd = measure_tunnelling(speed, ccd=True)
        without = measure_tunnelling(speed, ccd=False)
        tunnel.append(
            {
                "speed": speed,
                "travel_in_diameters": travel / MARBLE_DIAMETER,
                "tunnelled_with_ccd": with_ccd,
                "tunnelled_without_ccd": without,
            }
        )
        print(f"  {travel / MARBLE_DIAMETER:5.2f} diameters/tick  "
              f"no CCD {without:2}/20   with CCD {with_ccd:2}/20")
    return {"rates": rows, "tunnelling": tunnel}


def section_entry() -> dict[str, Any]:
    _header("Entry speeds into the bowl")
    spec = StartSpec()
    bowl_spec = start_bowl_curve().modules["bowl"].spec
    radius = bowl_spec.entry_radius
    orbit = math.sqrt(GRAVITY * radius * bowl_spec.slope(radius) / 1.4)
    replay = simulate(seed=7, machine=start_bowl_curve())
    speeds = entry_speeds(replay)
    # The measurement that decides whether the entry speed is safe is not the
    # speed - it is how far up the wall a marble actually climbs. The speed is
    # measured where a marble crosses the bowl's boundary rather than where the
    # spout lets go of it, so comparing it to the orbit speed is indicative and
    # the peak radius is decisive.
    peak = max(entry.peak_radius for entry in revolutions(replay))
    headroom = bowl_spec.max_radius - peak
    print(f"  circular-orbit speed at the release radius {radius:.2f}: {orbit:.2f} wu/s")
    print(f"  measured entry speeds: "
          f"{min(speeds.values()):.1f} to {max(speeds.values()):.1f} wu/s "
          f"({min(speeds.values()) / orbit:.2f} to {max(speeds.values()) / orbit:.2f} of orbit)")
    print(f"  furthest any marble climbed: {peak:.2f}, against a dish edge at "
          f"{bowl_spec.max_radius:.2f} - {headroom:.2f} wu of headroom")
    if headroom <= 0.0:
        print("  WARNING: a marble reached the edge of the dish and may leave the bowl")
    return {
        "orbit_speed": orbit,
        "release_radius": radius,
        "entry_speeds": {str(k): v for k, v in sorted(speeds.items())},
        "peak_radius": peak,
        "dish_edge": bowl_spec.max_radius,
        "headroom": headroom,
        "shelf_slope": spec.shelf_slope,
    }


def section_behaviour(seeds=SEEDS) -> dict[str, Any]:
    _header(f"Bowl behaviour and drain, over {len(seeds)} seeds")
    rows = []
    for seed in seeds:
        replay = simulate(seed=seed, machine=start_bowl_curve())
        summary = summarise(replay)
        turns = revolutions(replay)
        rows.append(
            {
                "seed": seed,
                "finished": summary["finished"],
                "escaped": summary["escaped"],
                "unfinished": summary["unfinished"],
                "sim_seconds": summary["sim_seconds"],
                "collisions": summary["collisions"],
                "revolutions": [entry.turns for entry in turns],
                "revolutions_median": summary["revolutions_median"],
                "peak_radius": max(entry.peak_radius for entry in turns) if turns else 0.0,
                "finish_order": summary["finish_order"],
                "max_energy_rise": summary["max_energy_rise"],
                "worst_penetration": summary["worst_penetration"],
                "failure": summary["failure"],
            }
        )
        print(f"  seed {seed:>4}  turns {summary['revolutions_median']:.2f}  "
              f"{summary['finished']}/8 out in {summary['sim_seconds']:.1f}s  "
              f"{summary['collisions']} collisions  "
              f"energy rise {summary['max_energy_rise']:.3g}  "
              f"order {summary['finish_order']}")
    medians = [row["revolutions_median"] for row in rows]
    orders = {tuple(row["finish_order"]) for row in rows}
    print(f"  median revolutions across seeds: {statistics.median(medians):.2f} "
          f"(the production 2D bowl measured 0.46; the lab's PyBullet prototype 4.06)")
    print(f"  distinct drain orders: {len(orders)}/{len(rows)}")
    print(f"  runs with an unexplained energy rise: "
          f"{sum(1 for row in rows if row['max_energy_rise'] > 1.0)}")
    return {"seeds": rows, "median_revolutions": statistics.median(medians),
            "distinct_orders": len(orders)}


def section_determinism(seeds=(7, 31), repeats: int = 20) -> dict[str, Any]:
    _header(f"Determinism: {repeats} same-process and {repeats} cross-process repeats")
    rows = []
    for seed in seeds:
        same = set()
        events = set()
        orders = set()
        for _ in range(repeats):
            replay = simulate(seed=seed, machine=start_bowl_curve())
            same.add(replay.digest())
            events.add(replay.event_digest())
            orders.add(tuple(replay.summary["finish_order"]))

        cross = set()
        cross_events = set()
        cross_orders = set()
        for _ in range(repeats):
            completed = subprocess.run(
                [sys.executable, "-m", "tools.marble3d_run", "--seed", str(seed), "--digest-only"],
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, "PYTHONPATH": os.getcwd()},
            )
            line = completed.stdout.strip().splitlines()[-1]
            digest, event_digest, order = line.split(" ", 2)
            cross.add(digest)
            cross_events.add(event_digest)
            # Parsed back into a tuple rather than kept as the printed string,
            # so the union below compares drain orders and not two spellings
            # of the same one.
            cross_orders.add(tuple(json.loads(order)))

        rows.append(
            {
                "seed": seed,
                "repeats": repeats,
                "same_process_digests": len(same),
                "cross_process_digests": len(cross),
                "same_process_event_digests": len(events),
                "cross_process_event_digests": len(cross_events),
                "drain_orders": len(orders | cross_orders),
                "agree": len(same | cross) == 1,
                "digest": sorted(same)[0],
            }
        )
        print(f"  seed {seed}: {len(same)} distinct state digest(s) in-process, "
              f"{len(cross)} across processes, "
              f"{len(events | cross_events)} event digest(s), "
              f"{len(orders | cross_orders)} drain order(s)")
        if len(same | cross) != 1:
            print("    FAIL: the same seed produced more than one trajectory")
    return {"seeds": rows, "environment": environment_metadata()}


def section_throughput() -> dict[str, Any]:
    _header("Headless throughput")

    def factory(count: int):
        """A chute long enough for `count` marbles, entering at the same speed.

        A longer queue on the same shelf is a taller queue, and at 64 marbles
        the back of it would start eight units higher than the front and arrive
        at the bowl well above orbit speed - it would climb over the dish edge,
        and the benchmark would be measuring escapes rather than throughput.
        Scaling the shelf's slope inversely with the count keeps the height
        spread, and so the entry speeds, the same at every field size, which is
        what makes the four rows comparable.
        """
        base = StartSpec()
        spec = StartSpec(
            marble_count=count,
            length=base.gate_offset + count * base.marble_spacing + 4.0,
            shelf_slope=base.shelf_slope * base.marble_count / count,
        )
        return start_bowl_curve(start=spec)

    rows = measure_throughput(factory)
    for row in rows:
        print(f"  {row['marbles']:>3} marbles  {row['wall_seconds']:6.2f}s wall  "
              f"{row['sim_seconds']:6.2f}s simulated  "
              f"{row['times_realtime']:6.2f}x realtime  "
              f"{row['finished']}/{row['marbles']} finished")
    if rows:
        base = rows[0]
        last = rows[-1]
        factor = last["marbles"] / base["marbles"]
        cost = last["wall_seconds"] / base["wall_seconds"]
        print(f"  {factor:.0f}x the marbles costs {cost:.1f}x the wall clock "
              f"(the lab's 2.5D model cost 15.5x for 8x)")
    return {"rows": rows}


# --- driver ---------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="every section")
    parser.add_argument("--colliders", action="store_true")
    parser.add_argument("--margins", action="store_true")
    parser.add_argument("--friction", action="store_true")
    parser.add_argument("--rates", action="store_true")
    parser.add_argument("--entry", action="store_true")
    parser.add_argument("--behaviour", action="store_true")
    parser.add_argument("--determinism", action="store_true")
    parser.add_argument("--throughput", action="store_true")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--report", nargs="?", const=DEFAULT_REPORT, default=None,
                        help="write the results as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    chosen = {
        "colliders": args.colliders,
        "margins": args.margins,
        "friction": args.friction,
        "rates": args.rates,
        "entry": args.entry,
        "behaviour": args.behaviour,
        "determinism": args.determinism,
        "throughput": args.throughput,
    }
    if args.all or not any(chosen.values()):
        chosen = {key: True for key in chosen}

    print(describe())
    report: dict[str, Any] = {"units": describe(), "environment": environment_metadata()}
    if chosen["colliders"]:
        report["colliders"] = section_colliders()
    if chosen["margins"]:
        report["margins"] = section_margins()
    if chosen["friction"]:
        report["friction"] = section_friction()
    if chosen["rates"]:
        report["rates"] = section_rates()
    if chosen["entry"]:
        report["entry"] = section_entry()
    if chosen["behaviour"]:
        report["behaviour"] = section_behaviour()
    if chosen["determinism"]:
        report["determinism"] = section_determinism(repeats=args.repeats)
    if chosen["throughput"]:
        report["throughput"] = section_throughput()

    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=2, sort_keys=False)
            handle.write("\n")
        print(f"\nreport written to {args.report}")

    failed = bool(report.get("colliders", {}).get("findings"))
    for row in report.get("determinism", {}).get("seeds", []):
        failed = failed or not row["agree"]
    for row in report.get("behaviour", {}).get("seeds", []):
        failed = failed or bool(row["failure"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

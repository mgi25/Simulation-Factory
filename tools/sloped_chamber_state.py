"""Measure the rotor chamber's field at the tick before the release opens.

    python tools/sloped_chamber_state.py --seeds 96
    python tools/sloped_chamber_state.py --seeds 96 --candidate rotor-fixed
    python tools/sloped_chamber_state.py --seeds 96 --json out.json

Section 2 of the V1.8 brief: before changing any geometry, find out how much
start identity is left in the chamber *before* release, and do not infer it
from exit statistics. Section 3 then reads a decision off this table - keep the
rotor untouched and change the release, or allow one small justified change to
the mixing first.

Each trial runs only to the release tick, which is about a quarter of a start
lab trial and none of its per-tick work, so 96 seeds is a minute.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sloped.chamberstate import sample_chamber, summarise_chamber  # noqa: E402
from sloped.startlab import (  # noqa: E402
    FLOOR_CANDIDATES,
    ROTOR_CANDIDATES,
    start_machine,
)

# Both chambers answer `gate_time` and both carry a rotor, so one
# instrument characterises either without a special case.
CANDIDATES = dict(ROTOR_CANDIDATES, **FLOOR_CANDIDATES)


def _build(candidate: str, mix: float | None, rate: float | None,
           settle: float | None):
    """One rotor machine, with the three knobs section 3 of the brief allows.

    `mix_seconds` and `rotor_rate` are constructor arguments; the settle is a
    class constant, set on the instance so it shadows the class and so
    `gate_time` - which is derived from it rather than typed - moves with it.
    """
    from sloped.startlab import FLOOR_CANDIDATES, ROTOR_CANDIDATES, start_machine

    plan = dict(ROTOR_CANDIDATES, **FLOOR_CANDIDATES)[candidate]
    if mix is not None or rate is not None:
        plan = replace(
            plan,
            mix_seconds=mix if mix is not None else plan.mix_seconds,
            rotor_rate=rate if rate is not None else plan.rotor_rate,
        )
    machine = start_machine(plan=plan)
    if settle is not None:
        machine.modules["start"].SETTLE_SECONDS = float(settle)
    return machine


def _one(job):
    """One seed, on a machine each worker builds once and keeps.

    Same pattern as `tools/sloped_start_bench.py`, and for the same reason: a
    `Machine` holds meshes, and rebuilding one per seed costs more than the
    trial does. The knobs are part of the cache key, so a worker cannot
    quietly reuse a machine built at a different mixing duration.
    """
    key = job[:-1]
    seed = job[-1]
    global _MACHINE
    try:
        cache = _MACHINE
    except NameError:
        cache = _MACHINE = {}
    machine = cache.get(key)
    if machine is None:
        cache.clear()
        machine = cache[key] = _build(*key)
    return sample_chamber(seed, machine=machine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        default="rotor-seeded",
        choices=sorted(CANDIDATES),
        help="which rotor configuration to characterise (default: the fairest)",
    )
    parser.add_argument(
        "--mix", type=float, default=None,
        help="override the mixing interval, in seconds",
    )
    parser.add_argument(
        "--rate", type=float, default=None,
        help="override the rotor rate, in rad/s",
    )
    parser.add_argument(
        "--settle", type=float, default=None,
        help="override the settle between the rotor stopping and the release",
    )
    parser.add_argument("--seeds", type=int, default=96)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--label", default="")
    parser.add_argument(
        "--samples", type=int, default=0,
        help="write this many per-seed raw samples into the JSON as well",
    )
    args = parser.parse_args(argv)

    key = (args.candidate, args.mix, args.rate, args.settle)
    probe = _build(*key)
    start = probe.modules["start"]
    # Warm the mesh cache in the parent, or seven workers race on the atomic
    # rename that installs a fresh collider OBJ - which on Windows raises
    # rather than finding the file already there.
    for module in probe:
        getattr(module, "local_colliders", list)()

    print(
        f"{args.label or 'chamber state'} [{args.candidate}]: sampling at "
        f"t={start.gate_time:.3f}s, the tick before the release opens"
    )
    print(
        f"  rotor turns {start.rotor_start:.3f}..{start.rotor_stop:.3f}s "
        f"({start.rotor_turns:.3f} turns, held for entry: {start.rotor_hold}), "
        f"settle {start.SETTLE_SECONDS}s"
    )

    jobs = [key + (seed,) for seed in range(args.first, args.first + args.seeds)]
    started = time.perf_counter()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            samples = list(pool.map(_one, jobs, chunksize=2))
    else:
        samples = [_one(job) for job in jobs]
    wall = time.perf_counter() - started

    # **Where the catch's exit is, in the chamber's own frame**, because that
    # is what a catch with one exit orders the field by. Read off the module
    # rather than typed.
    #
    # For both chambers in the tree the exit is on the chamber's own axis - a
    # 1.90 outlet under the rotor for `ShuffleChamber`, a 1.90 throat under the
    # cone for `ShuffleFloor` - so the drain distance *is* the radius column
    # and reporting it separately would be reporting the same number twice.
    # It is passed anyway, so that a catch whose exit moves off the axis is
    # measured for it rather than assumed about: the first build of the
    # full-floor release drained to a notch on its rim and that one change took
    # the centre-versus-rank correlation to +0.886.
    drain = (0.0, 0.0)
    if hasattr(start, "spill_z"):
        drain = (0.0, start.spill_z - start.CHAMBER_Z)
    report = summarise_chamber(samples, drain=drain)
    report["candidate"] = args.candidate
    report["mix_seconds"] = start.mix_seconds
    report["rotor_rate"] = start.rotor_rate
    report["settle_seconds"] = start.SETTLE_SECONDS
    report["label"] = args.label
    report["seeds"] = [args.first, args.first + args.seeds]
    report["sample_time"] = round(start.gate_time, 5)
    report["wall_seconds"] = round(wall, 2)
    report["chamber"] = probe.modules["start"].describe()["chamber"]

    print(
        f"  {report['trials']} trials in {wall:.1f}s; "
        f"{report['in_chamber']} of {report['racers']} racers in the chamber "
        f"({report['in_chamber_pct']}%)"
    )
    print()
    header = ("slot | racers |  radius |       x |       z |   speed | "
              "bearing | concentration |   drain")
    print(header)
    print("-" * len(header))
    for row in report["slots"]:
        def maybe(value, fmt="7.3f"):
            return format(value, fmt) if value is not None else "      -"
        print(
            f"  {row['slot']}  |   {row['racers']:>4} | {maybe(row['mean_radius'])} | "
            f"{maybe(row['mean_x'])} | {maybe(row['mean_z'])} | {maybe(row['mean_speed'])}"
            f" | {maybe(row['bearing_mean_deg'], '7.1f')} | "
            f"{maybe(row['bearing_resultant'], '13.3f')} | "
            f"{maybe(row['mean_drain'])}"
        )
    print("-" * len(header))

    def show(value, fmt="+.3f"):
        return "  n/a" if value is None else format(value, fmt)

    print()
    print("how much of the starting bay is left in the chamber:")
    print(f"  bay -> x                    r  {show(report['bay_to_x_r'])}"
          f"    (the bays are laid out along x)")
    print(f"  bay -> z                    r  {show(report['bay_to_z_r'])}")
    print(f"  bay -> radius               r  {show(report['bay_to_radius_r'])}")
    print(f"  |bay-3.5| -> radius         r  {show(report['centre_to_radius_r'])}")
    print(f"  bay -> speed                r  {show(report['bay_to_speed_r'])}")
    print(f"  bay -> (x, z) magnitude     r   {show(report['bay_to_plan_r'], '.3f')}"
          f"    (invariant to how far the field was carried round)")
    print(f"  bay -> bearing              R   {show(report['bay_to_bearing_R'], '.3f')}"
          f"    (circular-linear, 0..1)")
    print(f"  bay -> blade sector         R   {show(report['bay_to_blade_sector_R'], '.3f')}"
          f"    (bearing folded into one blade pitch)")
    if report["drain"] is not None:
        print(f"  bay -> drain distance       r  {show(report['bay_to_drain_r'])}"
              f"    (what a catch with one exit reads)")
        print(f"  |bay-3.5| -> drain distance r  "
              f"{show(report['centre_to_drain_r'])}"
              f"    (the shape a centre bias takes)")
        print(f"  drain order kept          rho  {show(report['drain_order_rho'])}")
    print(f"  lateral order kept        rho  {show(report['lateral_order_rho'])}"
          f"    (1.0 = the field is still in bay order across x)")
    print(f"  radial order kept         rho  {show(report['radial_order_rho'])}")
    print(f"  cyclic order agreement          {show(report['cyclic_order_agreement'], '.4f')}"
          f"   (0.5 = broken, 1.0 = the necklace merely rotated)")
    print(f"  cyclic order retained           {show(report['cyclic_order_retained'], '.4f')}"
          f"   over {report['cyclic_triples']} triples")
    print()
    print(
        f"  bearing concentration per bay: mean "
        f"{show(report['bearing_resultant_mean'], '.3f')}, worst "
        f"{show(report['bearing_resultant_max'], '.3f')}, against a uniform-angle "
        f"noise floor of {show(report['bearing_noise_floor'], '.3f')}"
    )
    print(
        f"  the eight bay mean bearings span "
        f"{show(report['bay_bearing_mean_span_deg'], '.1f')} deg; the field as a "
        f"whole prefers {show(report['field_bearing_mean_deg'], '.1f')} deg at "
        f"concentration {show(report['field_bearing_resultant'], '.3f')}"
    )
    print()
    if report["drain"] is not None:
        print(f"  mean drain distance {report['mean_drain']} (span across bays "
              f"{report['drain_span']}), exit at chamber-relative z "
              f"{report['drain'][1]}")
    print(f"  mean radius {report['mean_radius']} (span across bays "
          f"{report['radius_span']}), mean x span {report['x_span']}, "
          f"mean speed {report['mean_speed']}")

    if args.json:
        if args.samples:
            report["raw"] = [s.to_json() for s in samples[: args.samples]]
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

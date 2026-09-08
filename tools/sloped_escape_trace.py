"""Where the field leaves the course, and with what, sample by sample.

    python tools/sloped_escape_trace.py --start-kind floor --seeds 48
    python tools/sloped_escape_trace.py --start-kind fan --seeds 48
    python tools/sloped_escape_trace.py --start-kind floor --seeds 48 --json out.json

A loss-site histogram says *where* a racer left; it does not say whether it went
over a guard, through a floor, or was already outside the channel when the
instrument first located it. Those are three different repairs, and the V1.8
start's launch escapes need the difference: the axial catch's 3.93 lift feeds
the launch's banked plunge faster, and the question is whether the marbles are
climbing the bank or arriving too high to be on it at all.

So this records, at the tick a racer is first outside containment: the run and
sample, how far across the channel it was as a fraction of the local half
width, how high above the local floor, its speed and the lateral and vertical
components of it, and the local grade and bank. Plus the *worst* height and
reach each racer reached whether or not it escaped, because a field that is
running at 90% of the guard everywhere is one bad seed from a loss and a
histogram cannot see that either.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marble3d.config import DEFAULT_CONFIG  # noqa: E402
from marble3d.units import MARBLE_RADIUS  # noqa: E402
from sloped.race import LATERAL_SLACK, VERTICAL_SLACK  # noqa: E402
from sloped.scale import SIM_TO_LAYOUT  # noqa: E402
from sloped.startlab import (  # noqa: E402
    BENCH_PLANS,
    FLOOR_CANDIDATES,
    LAB_CHECKPOINTS,
    ROTOR_CANDIDATES,
    StartTrial,
    seed_phase_for,
    start_machine,
)

CANDIDATES = dict(ROTOR_CANDIDATES, **FLOOR_CANDIDATES)


class EscapeTrial(StartTrial):
    """A start-lab trial that says *how* a racer left, not just that it did.

    `_containment` is overridden rather than copied: the base class decides
    the verdict and this records the state at the moment it does, so the two
    cannot drift apart. The peak columns are collected on every sampled tick.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.escapes: dict[int, dict] = {}
        self.peak_height: dict[int, float] = {mid: -9.9 for mid in self.slot_of}
        self.peak_reach: dict[int, float] = {mid: 0.0 for mid in self.slot_of}

    def _containment(self, marble_id, position):
        place = self._where.get(marble_id)
        already = marble_id in self.lost
        super()._containment(marble_id, position)
        if place is None:
            return
        name, index = place
        run = self.runs[name]
        lateral, up, forward = run.frames[index]
        centre = run.sim_path[index]
        offset = [position[axis] - centre[axis] for axis in range(3)]
        across = sum(offset[axis] * lateral[axis] for axis in range(3))
        height = sum(offset[axis] * up[axis] for axis in range(3))
        half = 0.5 * run.clear_width * run.widths[index]
        self.peak_height[marble_id] = max(
            self.peak_height[marble_id], height * SIM_TO_LAYOUT
        )
        self.peak_reach[marble_id] = max(
            self.peak_reach[marble_id], abs(across) / max(half, 1e-9)
        )
        if already or marble_id not in self.lost:
            return
        velocity = self.sim.marbles[marble_id].pose[2]
        across_v = sum(velocity[axis] * lateral[axis] for axis in range(3))
        up_v = sum(velocity[axis] * up[axis] for axis in range(3))
        along_v = sum(velocity[axis] * forward[axis] for axis in range(3))
        bank = run.banks[index] if hasattr(run, "banks") else 0.0
        self.escapes[marble_id] = {
            "run": name,
            "sample": index,
            "pct": round(100.0 * index / max(len(run.sim_path) - 1, 1), 1),
            "slot": self.slot_of[marble_id],
            "across": round(across * SIM_TO_LAYOUT, 4),
            "reach": round(across / max(half, 1e-9), 4),
            "height": round(height * SIM_TO_LAYOUT, 4),
            "containment": round(run.containment * SIM_TO_LAYOUT, 4),
            "over_by": round((height - run.containment) * SIM_TO_LAYOUT, 4),
            "wide_by": round(
                (abs(across) - half - LATERAL_SLACK) * SIM_TO_LAYOUT, 4
            ),
            "speed": round(math.hypot(*velocity) * SIM_TO_LAYOUT, 3),
            "across_speed": round(across_v * SIM_TO_LAYOUT, 3),
            "up_speed": round(up_v * SIM_TO_LAYOUT, 3),
            "along_speed": round(along_v * SIM_TO_LAYOUT, 3),
            "bank_deg": round(math.degrees(bank), 2),
            "tick": self.sim.ticks,
            # **Two independent facts, because one label conflated them.**
            #
            # `which_test` is the base class's own disjunction: a racer is lost
            # when it is `LATERAL_SLACK` outside the half width *or*
            # `VERTICAL_SLACK` above the containment. The first version of this
            # tool reported "over the guard" only when the *vertical* test
            # fired, and so labelled eleven of twelve escapes "outside the
            # wall" - marbles whose centres were above the 0.80 guard top and
            # 0.3 outside its face, which is over the guard by any reading. The
            # vertical slack is a whole marble diameter, so a racer can be
            # comfortably over the guard and still trip the lateral test first.
            #
            # `above_guard` is the physical question: is the centre higher than
            # the guard's top? That is what says a guard or a bank is the
            # repair rather than a floor or a join.
            "which_test": (
                "lateral" if abs(across) > half + LATERAL_SLACK else "vertical"
            ),
            "above_guard": bool(height > run.containment),
            "verdict": (
                "over the guard" if height > run.containment
                else "outside the wall, below the guard top"
            ),
        }


def _apply_slopes(chute_grade, funnel_tilt):
    """The two start-side slope knobs section 1 of the brief allows.

    **Set on the class rather than the instance**, because `derived_lift` reads
    them from `__init__` - so an instance attribute is written after the height
    chain has already been computed from the old values, which is the silent
    way to measure the wrong geometry.
    """
    from sloped.trapdoor import ShuffleFloor

    if chute_grade is not None:
        ShuffleFloor.CHUTE_GRADE = float(chute_grade)
    if funnel_tilt is not None:
        ShuffleFloor.FUNNEL_TILT = float(funnel_tilt)


def _one(job):
    kind, candidate, seed, duration, chute_grade, funnel_tilt = job
    global _MACHINE
    try:
        cache = _MACHINE
    except NameError:
        cache = _MACHINE = {}
    key = (kind, candidate, chute_grade, funnel_tilt)
    machine = cache.get(key)
    if machine is None:
        from sloped.startlab import BENCH_PLANS, FLOOR_CANDIDATES, ROTOR_CANDIDATES

        cache.clear()
        _apply_slopes(chute_grade, funnel_tilt)
        table = dict(ROTOR_CANDIDATES, **FLOOR_CANDIDATES)
        plan = table[candidate] if candidate else BENCH_PLANS[kind]
        machine = cache[key] = start_machine(plan=plan)
    plan = getattr(machine, "plan", None)
    start = machine.modules.get("start")
    if plan is not None and getattr(plan, "seed_phase", False):
        start.rotor_phase = seed_phase_for(seed)
    release = 0.0
    for module in machine:
        for actuator in getattr(module, "local_actuators", lambda: [])():
            release = max(
                release,
                getattr(actuator, "release_time", 0.0)
                + getattr(actuator, "duration", 0.0),
            )
    config = DEFAULT_CONFIG
    trial = EscapeTrial(machine, config, seed, 8)
    limit = int(round((duration + release) * config.physics.physics_hz))
    try:
        while trial.sim.ticks < limit and not trial.settled():
            trial.step()
        return {
            "seed": seed,
            "escapes": list(trial.escapes.values()),
            "stuck": [
                {"slot": trial.slot_of[mid], "run": place[0], "sample": place[1]}
                for mid, place in trial.stuck.items()
            ],
            "peak_height": max(trial.peak_height.values()),
            "peak_reach": max(trial.peak_reach.values()),
        }
    finally:
        trial.sim.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-kind", required=True, choices=list(BENCH_PLANS))
    parser.add_argument("--candidate", default=None, choices=sorted(CANDIDATES))
    parser.add_argument("--seeds", type=int, default=48)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--duration", type=float, default=14.0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--label", default="")
    parser.add_argument(
        "--chute-grade", type=float, default=None,
        help="override the floor start's exit chute grade, in degrees",
    )
    parser.add_argument(
        "--funnel-tilt", type=float, default=None,
        help="override the floor start's catch cone tilt, in degrees",
    )
    args = parser.parse_args(argv)

    _apply_slopes(args.chute_grade, args.funnel_tilt)
    if args.candidate and CANDIDATES[args.candidate].start_kind != args.start_kind:
        parser.error(
            f"candidate {args.candidate!r} is a "
            f"{CANDIDATES[args.candidate].start_kind!r} plan"
        )
    probe = start_machine(
        plan=CANDIDATES[args.candidate] if args.candidate else BENCH_PLANS[args.start_kind]
    )
    if probe.start_kind != args.start_kind:               # pragma: no cover
        raise AssertionError(f"asked for {args.start_kind!r}, got {probe.start_kind!r}")
    for module in probe:
        getattr(module, "local_colliders", list)()

    jobs = [
        (args.start_kind, args.candidate, seed, args.duration,
         args.chute_grade, args.funnel_tilt)
        for seed in range(args.first, args.first + args.seeds)
    ]
    started = time.perf_counter()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(_one, jobs, chunksize=2))
    else:
        results = [_one(job) for job in jobs]
    wall = time.perf_counter() - started

    escapes = [row for result in results for row in result["escapes"]]
    stuck = [row for result in results for row in result["stuck"]]
    racers = 8 * len(results)
    print(
        f"{args.label or 'escape trace'} [{args.start_kind}"
        f"{'' if not args.candidate else '/' + args.candidate}]: {len(results)} "
        f"seeds, {racers} racers in {wall:.1f}s"
    )
    print(
        f"  {len(escapes)} left the course ({100.0 * len(escapes) / racers:.3f}%), "
        f"{len(stuck)} stopped"
    )
    start = probe.modules.get("start")
    if hasattr(start, "panel_well"):
        print(
            f"  start lift {start.lift:.3f}; the field falls "
            f"{start.pan_floor - (start.exit_local[1] + 0.0):.3f} from the pan to "
            f"the launch seat, cone {start.FUNNEL_TILT:.1f} deg, chute "
            f"{start.CHUTE_GRADE:.1f} deg"
        )
    print(
        f"  worst height reached {max(r['peak_height'] for r in results):.3f} "
        f"against a containment of {probe.runs['launch'].containment * SIM_TO_LAYOUT:.3f}; "
        f"worst reach {max(r['peak_reach'] for r in results):.3f} of the half width"
    )
    if escapes:
        print()
        verdicts = Counter(row["verdict"] for row in escapes)
        for verdict, count in verdicts.most_common():
            print(f"  {count:3} {verdict}")
        tests = Counter(row["which_test"] for row in escapes)
        print("  the test that fired first: "
              + ", ".join(f"{k} x{v}" for k, v in tests.most_common()))
        by_run = Counter(row["run"] for row in escapes)
        print("  by run: " + ", ".join(f"{k} x{v}" for k, v in by_run.most_common()))
        print()
        header = ("  run    sample   %  slot | reach  height  over  | speed "
                  "across    up | bank | verdict")
        print(header)
        print("  " + "-" * (len(header) - 2))
        for row in sorted(escapes, key=lambda r: (r["run"], r["sample"])):
            print(
                f"  {row['run']:<6} {row['sample']:5}{row['pct']:6.1f} "
                f"{row['slot']:5} | {row['reach']:+.2f}  {row['height']:+.3f} "
                f"{row['over_by']:+.3f} | {row['speed']:5.1f} "
                f"{row['across_speed']:+6.1f} {row['up_speed']:+5.1f} | "
                f"{row['bank_deg']:+5.1f} | {row['which_test']:<8} "
                f"{'above the guard' if row['above_guard'] else 'below its top'}"
            )
        print("  " + "-" * (len(header) - 2))
        sites = Counter(f"{row['run']}[{row['sample'] // 10 * 10}..]" for row in escapes)
        print("  by sample band: "
              + ", ".join(f"{k} x{v}" for k, v in sites.most_common(8)))
    if stuck:
        print()
        sites = Counter(f"{row['run']}[{row['sample']}]" for row in stuck)
        print("  stopped at: "
              + ", ".join(f"{k} x{v}" for k, v in sites.most_common(8)))

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "start_kind": args.start_kind,
                    "candidate": args.candidate,
                    "label": args.label,
                    "seeds": [args.first, args.first + args.seeds],
                    "racers": racers,
                    "escapes": escapes,
                    "stuck": stuck,
                    "peak_height": max(r["peak_height"] for r in results),
                    "peak_reach": max(r["peak_reach"] for r in results),
                    "wall_seconds": round(wall, 2),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

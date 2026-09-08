"""Does one seed give one race? Twenty times in this process, twenty in fresh ones.

    python tools/sloped_determinism.py --seed 31 --repeats 20

Section 46. Two questions, and they are not the same question:

**In process.** Twenty runs in one interpreter. This catches state that leaks
between runs - a module caching something it should not, a random stream not
re-derived from the seed, a dictionary iterated in insertion order that differs
because the previous run inserted something.

**Across processes.** Twenty runs in fresh interpreters. This is the one the
physics lab established matters: without `deterministicOverlappingPairs` the
broadphase pair order depends on allocation addresses, so the same seed gives
different answers in different processes and every determinism claim rests on
that flag being set. `marble3d.world` sets it and this is what proves it.

Compared, in this order: the state digest, the event digest, the **actuator**
digest, the finish order, the finish times, the route and start slot of every
racer, and the race duration. The actuator digest is its own thing because the
state digest does not cover the machine's moving parts at all - see
`marble3d.replay.Replay.actuator_digest`. The state digest is
a SHA-256 over the raw IEEE-754 bytes of the sampled state taken *before* the
numbers are rounded for storage, so it cannot be fooled by two trajectories
that agree to six decimals at one instant and are elsewhere entirely by tick
two thousand.

**Cross machine is not tested and is not claimed.** There is one machine here.
What the report carries instead is `environment_metadata` - platform, processor,
Python and PyBullet build - so two runs taken a year apart on two continents
can be compared as evidence rather than as a coincidence. That is also why the
pipeline ships a *replay* rather than a seed: the seed is chosen on the machine
that simulates it and what travels to the machine that renders it is the file.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG
from marble3d.simulation import environment_metadata
from sloped.course import sloped_course
from sloped.race import run_race


def one_run(seed: int, marbles: int, duration: float, routes: str) -> dict[str, Any]:
    outcome, replay = run_race(
        seed=seed,
        machine=sloped_course(routes=routes),
        marble_count=marbles,
        duration=duration,
        with_replay=True,
    )
    return {
        "digest": replay.digest(),
        "event_digest": replay.event_digest(),
        # The machine's own moving parts, which `digest` does not cover at all.
        # See `Replay.actuator_digest`: the frozen start carries a rotor whose
        # initial angle comes from the seed and eighteen sweeping floor slats,
        # and a replay a renderer draws those from has to be pinned as tightly
        # as the marbles are.
        "actuator_digest": replay.actuator_digest(),
        "seconds": round(outcome.seconds, 9),
        "frames": len(replay.frames),
        "order": [
            r.marble_id
            for r in sorted(
                (r for r in outcome.racers if r.finish_order),
                key=lambda r: r.finish_order,
            )
        ],
        "times": [
            round(r.finish_time, 9)
            for r in sorted(
                (r for r in outcome.racers if r.finish_order),
                key=lambda r: r.finish_order,
            )
        ],
        "routes": {str(r.marble_id): r.route for r in outcome.racers},
        "slots": {str(r.marble_id): r.start_slot for r in outcome.racers},
    }


def child_run(seed: int, marbles: int, duration: float, routes: str) -> dict[str, Any]:
    """One run in a fresh interpreter, reported over stdout as one JSON line."""
    completed = subprocess.run(
        [
            sys.executable,
            os.path.abspath(__file__),
            "--child",
            "--seed",
            str(seed),
            "--marbles",
            str(marbles),
            "--duration",
            str(duration),
            "--routes",
            routes,
        ],
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONPATH": os.getcwd()},
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"child exited {completed.returncode}\n{(completed.stderr or '')[-1200:]}"
        )
    for line in reversed((completed.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"child printed no result\n{(completed.stdout or '')[-800:]}")


KEYS = ("digest", "event_digest", "actuator_digest", "seconds", "frames",
        "order", "times", "routes", "slots")


def compare(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    reference = runs[0]
    disagreements: dict[str, list[int]] = {}
    for index, run in enumerate(runs[1:], start=1):
        for key in KEYS:
            if run[key] != reference[key]:
                disagreements.setdefault(key, []).append(index)
    return {
        "runs": len(runs),
        "identical": not disagreements,
        "disagreements": disagreements,
        "reference": {
            key: reference[key]
            for key in ("digest", "event_digest", "actuator_digest", "seconds", "order")
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=DEFAULT_CONFIG.duration_limit)
    parser.add_argument("--routes", default="blue")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    if args.child:
        print(json.dumps(one_run(args.seed, args.marbles, args.duration, args.routes)))
        return 0

    print(f"seed {args.seed}, {args.repeats} in process then {args.repeats} in children")
    started = time.perf_counter()
    in_process = []
    for index in range(args.repeats):
        in_process.append(one_run(args.seed, args.marbles, args.duration, args.routes))
        print(f"  in-process {index + 1}/{args.repeats}", file=sys.stderr, flush=True)
    same_process = compare(in_process)

    children = []
    for index in range(args.repeats):
        children.append(child_run(args.seed, args.marbles, args.duration, args.routes))
        print(f"  child {index + 1}/{args.repeats}", file=sys.stderr, flush=True)
    fresh_process = compare(children)
    across = compare([in_process[0], children[0]])

    report = {
        "seed": args.seed,
        "marbles": args.marbles,
        "duration": args.duration,
        "routes": args.routes,
        "physics_hz": DEFAULT_CONFIG.physics.physics_hz,
        "config": DEFAULT_CONFIG.to_json(),
        "environment": environment_metadata(),
        "in_process": same_process,
        "fresh_process": fresh_process,
        "in_process_vs_fresh": across,
        "cross_machine": (
            "not tested: one machine was available. The environment block above "
            "is what a second machine's report would be diffed against."
        ),
        "wall_seconds": round(time.perf_counter() - started, 3),
    }

    print(
        f"in process:   {same_process['runs']} runs, "
        f"{'identical' if same_process['identical'] else same_process['disagreements']}"
    )
    print(
        f"fresh process: {fresh_process['runs']} runs, "
        f"{'identical' if fresh_process['identical'] else fresh_process['disagreements']}"
    )
    print(
        f"one against the other: "
        f"{'identical' if across['identical'] else across['disagreements']}"
    )
    print(f"digest {same_process['reference']['digest']}")
    print(f"events {same_process['reference']['event_digest']}")
    print(f"actors {same_process['reference']['actuator_digest']}")
    print(f"order  {same_process['reference']['order']}")
    print(f"{report['wall_seconds']:.0f} s wall")

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"wrote {args.out}")
    ok = same_process["identical"] and fresh_process["identical"] and across["identical"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Trace the full-floor release in simulation, one marble at a time upward.

    python tools/sloped_floor_trace.py --stage a
    python tools/sloped_floor_trace.py --stage b
    python tools/sloped_floor_trace.py --stage c --seeds 12
    python tools/sloped_floor_trace.py --stage b --json out.json

Section 11 of the V1.8 brief sets the order and says why: do not run 500 seeds
at a new mechanism. So:

    a   one stationary marble, at a spread of chamber positions, one per run.
        The floor opens under it and nothing else is in the way. This is the
        cheapest thing that can see a slat throw a marble, or a slat leave one
        where it was, or a dish let one out.
    b   eight stationary marbles distributed round the chamber, all released
        together. Same question with traffic.
    c   the real thing: the bays, the gate, the apron and the rotor, over a
        handful of seeds.

Stages a and b place marbles **in the chamber directly**, with the pan, the
gate and the rotor left out of the question, by overriding the module's own
`marble_starts`. That is the same trick `tools/sloped_radial_trace.py` uses and
it is on the instance rather than on a copy, because `local_actuators` and
`marble_starts` are read when the simulation is built.

What is reported per marble: whether it was released at all, how far it fell,
whether it stopped on the catch or went through it, and its top speed. Those
are the three states this tool can see honestly. **Containment is not one of
them** - it needs the run's own frame at the marble's own sample, so stage D's
`sloped.startlab.StartTrial` is what answers it, and two attempts at a depth
threshold here were both wrong in the direction that either flatters or libels
the mechanism.
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
from sloped.chamberstate import _to_local  # noqa: E402
from sloped.scale import SIM_TO_LAYOUT  # noqa: E402
from sloped.startlab import FLOOR_CANDIDATES, start_machine  # noqa: E402
from sloped.trapdoor import ShuffleFloor  # noqa: E402
from sloped.track import TrackRun  # noqa: E402

# Where stage A puts its single marble: a spread that covers the cases the
# geometry check cannot answer. Radius as a fraction of the free radius, and
# bearing in degrees. Every combination is run on its own.
STAGE_A = [
    (0.0, 0.0),          # dead centre, over the open middle of the chamber
    (0.45, 0.0),
    (0.45, 90.0),
    (0.45, 180.0),
    (0.45, 270.0),       # under the inlet
    (0.95, 0.0),         # hard against the wall, four ways
    (0.95, 90.0),
    (0.95, 180.0),
    (0.95, 270.0),
    (0.95, 45.0),
    (0.95, 135.0),
    (0.70, 30.0),
    (0.70, 210.0),
    # On a seam, and on a hinge line: the two places a louvre could hold a
    # marble that its middle cannot.
    (0.60, 0.0),
    (0.60, 180.0),
]

# **Hard against the wall, at every bearing.** Added after stage C: two racers
# of 96 were never released, both at radius 2.412 against a free radius of
# 2.415, and 0.95 of the way out was not enough to reproduce it. A failure that
# only happens at the very limit still happens, and it needs a case that puts a
# marble there on purpose rather than a seed that occasionally does.
STAGE_A += [(1.0, bearing) for bearing in range(0, 360, 20)]


def _seat(floor: ShuffleFloor, radius_fraction: float, bearing_deg: float):
    """A resting marble centre in the chamber, in the module's local frame."""
    free = floor.R_WALL - layout.MARBLE_RADIUS
    radius = free * radius_fraction
    angle = math.radians(bearing_deg)
    return (
        radius * math.cos(angle),
        floor.rim_floor + layout.MARBLE_RADIUS,
        floor.CHAMBER_Z + radius * math.sin(angle),
    )


def _seam_points(floor: ShuffleFloor):
    """Chamber positions sitting exactly on a slat seam and on a hinge.

    Reported separately in stage B because they are the positions a louvre can
    fail at and its middle cannot: a marble straddling two slats is supported
    by both and released by both, and one sitting over a hinge line is over the
    only part of a slat that does not move.
    """
    points = []
    for index in range(1, floor.PANELS):
        z = -floor.R_WALL + index * floor.panel_pitch
        limit = floor.R_WALL - layout.MARBLE_RADIUS
        if abs(z) >= limit:
            continue
        reach = math.sqrt(limit * limit - z * z)
        for across in (0.0, 0.6 * reach):
            points.append((across, floor.rim_floor + layout.MARBLE_RADIUS,
                           floor.CHAMBER_Z + z))
    return points


def build_bare(seats, candidate: str = "floor-tuned") -> tuple[Machine, ShuffleFloor]:
    """The floor start with the launch and leg1 behind it, seeded in-chamber.

    The downstream is kept because the question "did it get out" needs
    somewhere to get out to, and because a marble that leaves the machine
    should be recorded as lost rather than as delivered.
    """
    machine = start_machine(plan=FLOOR_CANDIDATES[candidate])
    floor = machine.modules["start"]
    rotation = floor._rotation()
    placed = [
        Transform(
            position=_place(floor, seat),
            rotation=rotation,
        )
        for seat in seats
    ]
    floor.marble_starts = lambda: placed       # type: ignore[method-assign]
    # The bay paddles are irrelevant to a marble already in the chamber, and a
    # paddle standing on the apron is one more thing in the way of reading the
    # result. The rotor is left in: the field has to fall past it.
    original = floor.local_actuators

    def without_paddles():
        return [a for a in original() if not a.name.startswith("paddle")]

    floor.local_actuators = without_paddles    # type: ignore[method-assign]
    return machine, floor


def _place(floor: ShuffleFloor, local):
    from sloped.stations import _place as place

    return place(floor.origin, floor.frame, local)


def run(machine: Machine, floor: ShuffleFloor, seed: int, duration: float,
        marble_count: int | None = None) -> list[dict]:
    """One run, reporting where each marble ended up and how it got there."""
    config = DEFAULT_CONFIG
    sim = MarbleSimulation(machine, config, seed, marble_count)
    ticks = int(round(duration * config.physics.physics_hz))
    open_tick = int(math.floor(floor.floor_open * config.physics.physics_hz))
    rows = {
        marble_id: {
            "marble": marble_id,
            "bay": marble.start_index,
            "top_speed": 0.0,
            "left_chamber_at": None,
            "min_y": 0.0,
        }
        for marble_id, marble in sim.marbles.items()
    }
    at_release: dict[int, tuple] = {}
    try:
        while sim.ticks < ticks:
            sim.step()
            if sim.ticks == open_tick:
                for marble_id, marble in sim.marbles.items():
                    at_release[marble_id] = _to_local(floor, marble.pose[0])
            if sim.ticks % 4:
                continue
            for marble_id, marble in sim.marbles.items():
                local = _to_local(floor, marble.pose[0])
                row = rows[marble_id]
                row["top_speed"] = max(
                    row["top_speed"], math.hypot(*marble.pose[2]) * SIM_TO_LAYOUT
                )
                row["min_y"] = min(row["min_y"], local[1])
                # Out of the chamber once it is half a unit below the floor
                # plane the slats used to be. Nothing resting in the chamber is
                # that low, and using the dish's *rim* instead calls a marble
                # sitting on the dish near its high edge "still in the
                # chamber" - which the first version of this tool did.
                if (row["left_chamber_at"] is None
                        and local[1] < floor.rim_floor - 0.5):
                    row["left_chamber_at"] = round(sim.ticks / 240.0, 4)
        for marble_id, marble in sim.marbles.items():
            local = _to_local(floor, marble.pose[0])
            row = rows[marble_id]
            start = at_release.get(marble_id)
            row["released_from"] = (
                None if start is None
                else [round(start[0], 3), round(start[2], 3)]
            )
            row["release_radius"] = (
                None if start is None
                else round(math.hypot(start[0], start[2] - floor.CHAMBER_Z), 3)
            )
            row["end"] = [round(v, 3) for v in local]
            row["fell"] = round(floor.rim_floor - local[1], 3)
            # **Three states, and the middle one is the interesting failure.**
            # `in_chamber` is never released. `past_spill` is through the notch
            # and away down the course. Anything else is sitting on the dish,
            # which is released but not delivered - and the first version of
            # this tool had no such column, calling a marble far down leg1
            # "left the machine" because it was below the dish's lip, and a
            # marble stopped on the dish "still in the chamber" because it was
            # above the dish's rim. Both readings were wrong in the direction
            # that flatters the mechanism.
            row["in_chamber"] = local[1] > floor.rim_floor - 0.5
            # **Through the throat**, which for a cone on the axis is a height
            # rather than a downstream distance: the throat's lip is the cone's
            # lowest surface, so anything below it has left the catch. A marble
            # resting anywhere on the cone is above it.
            row["past_spill"] = local[1] < floor.dish_lip
            row["on_dish"] = not row["in_chamber"] and not row["past_spill"]
            # **There is deliberately no escape column.** Two attempts at one
            # were both wrong in this tool: a depth threshold called a marble
            # 34 units down leg1 "left the machine", and moving the threshold
            # with the lift made it fire on every delivered racer. Containment
            # needs the run's own frame at the marble's own sample, which is
            # what `sloped.startlab.StartTrial._containment` does with the
            # channel width and the guard height - so that is the instrument
            # that answers it, in stage D, and this one reports the three
            # states it can actually see.
            row["escaped"] = False
            row["top_speed"] = round(row["top_speed"], 2)
            row["min_y"] = round(row["min_y"], 3)
        return [rows[key] for key in sorted(rows)]
    finally:
        sim.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("a", "b", "c"), default="a")
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--candidate", default="floor-tuned",
                        choices=sorted(FLOOR_CANDIDATES))
    parser.add_argument("--duration", type=float, default=None,
                        help="seconds to run; the default is the release plus 6")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    probe = ShuffleFloor("start", TrackRun("launch"))
    duration = args.duration or (probe.floor_open + 6.0)
    report: dict = {
        "stage": args.stage,
        "candidate": args.candidate,
        "duration": duration,
        "floor_open": round(probe.floor_open, 4),
        "runs": [],
    }
    print(f"floor trace, stage {args.stage} [{args.candidate}]: the floor opens "
          f"at {probe.floor_open:.2f}s, running to {duration:.2f}s")

    if args.stage == "a":
        header = ("  from (r, deg) | released | fell  | end z  | top v | verdict")
        print(header)
        print("  " + "-" * (len(header) - 2))
        held = escaped = 0
        for fraction, bearing in STAGE_A:
            machine, floor = build_bare(
                [_seat(probe, fraction, bearing)], args.candidate
            )
            rows = run(machine, floor, seed=0, duration=duration)
            row = rows[0]
            verdict = (
                "NEVER RELEASED" if row["in_chamber"]
                else "LEFT THE MACHINE" if row["escaped"]
                else "delivered, and away down the course" if row["past_spill"]
                else "STOPPED ON THE DISH"
            )
            held += bool(row["in_chamber"]) or bool(row["on_dish"])
            escaped += bool(row["escaped"])
            print(f"   {fraction:4.2f}, {bearing:5.0f}   |"
                  f" {str(row['left_chamber_at'] or '-'):>8} |"
                  f" {row['fell']:5.2f} | {row['end'][2]:6.2f} |"
                  f" {row['top_speed']:5.1f} | {verdict}")
            report["runs"].append(
                {"from": [fraction, bearing], "rows": rows}
            )
        print("  " + "-" * (len(header) - 2))
        print(f"  {len(STAGE_A)} positions: {held} not delivered, "
              f"{escaped} left the machine")
        report["held"] = held
        report["escaped"] = escaped

    elif args.stage == "b":
        seats = [_seat(probe, fraction, bearing) for fraction, bearing in
                 ((0.90, 0.0), (0.90, 90.0), (0.90, 180.0), (0.90, 270.0),
                  (0.45, 45.0), (0.45, 135.0), (0.45, 225.0), (0.45, 315.0))]
        groups = {"ring and inner": seats, "on the seams": _seam_points(probe)[:8]}
        for label, group in groups.items():
            machine, floor = build_bare(group, args.candidate)
            rows = run(machine, floor, seed=0, duration=duration,
                       marble_count=len(group))
            held = sum(1 for r in rows if r["in_chamber"])
            stalled = sum(1 for r in rows if r["on_dish"])
            escaped = sum(1 for r in rows if r["escaped"])
            past = sum(1 for r in rows if r["past_spill"])
            print(f"\n  {label}: {len(rows)} marbles, {past} delivered, {held} "
                  f"never released, {stalled} stopped on the dish, {escaped} "
                  f"left the machine")
            header = "  marble | released | fell  |    end (x, y, z)     | top v"
            print(header)
            print("  " + "-" * (len(header) - 2))
            for row in rows:
                print(f"     {row['marble']}    |"
                      f" {str(row['left_chamber_at'] or '-'):>8} |"
                      f" {row['fell']:5.2f} |"
                      f" {row['end'][0]:6.2f} {row['end'][1]:6.2f}"
                      f" {row['end'][2]:6.2f} | {row['top_speed']:5.1f}")
            report["runs"].append({"group": label, "rows": rows})

    else:
        machine = start_machine(plan=FLOOR_CANDIDATES[args.candidate])
        floor = machine.modules["start"]
        from sloped.startlab import seed_phase_for

        totals = {"held": 0, "escaped": 0, "past": 0, "racers": 0}
        header = "  seed | released | held | dish | left | delivered | top v"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for seed in range(args.seeds):
            floor.rotor_phase = seed_phase_for(seed)
            rows = run(machine, floor, seed=seed, duration=duration)
            held = sum(1 for r in rows if r["in_chamber"])
            stalled = sum(1 for r in rows if r["on_dish"])
            escaped = sum(1 for r in rows if r["escaped"])
            past = sum(1 for r in rows if r["past_spill"])
            released = sum(1 for r in rows if r["left_chamber_at"] is not None)
            top = max(r["top_speed"] for r in rows)
            totals["held"] += held
            totals["stalled"] = totals.get("stalled", 0) + stalled
            totals["escaped"] += escaped
            totals["past"] += past
            totals["racers"] += len(rows)
            print(f"   {seed:4} | {released:8} | {held:4} | {stalled:4} |"
                  f" {escaped:4} | {past:9} | {top:5.1f}")
            report["runs"].append({"seed": seed, "rows": rows})
        print("  " + "-" * (len(header) - 2))
        racers = totals["racers"]
        print(f"  {racers} racers: {totals['past']} delivered "
              f"({100.0 * totals['past'] / racers:.2f}%), {totals['held']} never "
              f"released, {totals.get('stalled', 0)} stopped on the dish, "
              f"{totals['escaped']} left the machine")
        report["totals"] = totals

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

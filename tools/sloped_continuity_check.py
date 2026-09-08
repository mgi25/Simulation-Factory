"""Audit every run for the local defects a marble leaves the course on.

    python tools/sloped_continuity_check.py
    python tools/sloped_continuity_check.py --run leg1 --from 70 --to 100
    python tools/sloped_continuity_check.py --json out.json

Section 4 of the V1.9 brief names the things to inspect at a concentrated loss
site - floor steps, tangent continuity, bank transitions, collider joins,
guards, local slope - and asks for them to be treated as local geometry
defects. This measures all of them, per sample, so the answer is a number
rather than an opinion.

What is reported per sample, in layout units and degrees:

* **turn radius**, from three consecutive centreline points projected on the
  horizontal plane, and **how high up the channel a marble at the judged speed
  rides through it** - read off the channel's own profile, with the bank added
  to each segment and its sign taken from which way the corner turns. That
  height compares directly against `containment`, so a site is a defect when
  the answer is "higher than the guard". It also reports when the bank is
  rolled the *wrong way* for its corner, which is a defect a radius alone
  cannot show.
* **tangent break**, the angle between consecutive segment directions. A spline
  through drawn control points can put a corner wherever it clamps, and a
  corner is a step the marble jumps rather than a curve it follows.
* **bank rate**, degrees of roll per layout unit of arc. Rolling faster than a
  marble can follow lifts it off the floor on the inside and drops it on the
  outside.
* **grade break**, the change in descent angle between consecutive segments.
* **floor step**, the height discontinuity between the end of one run's
  cradle and the start of the next, in the shared frame - which is what
  "collider join" means for two swept meshes that meet at a socket.

Nothing here runs a simulation. It is the gate before one.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sloped import layout  # noqa: E402
from sloped.course import CHAIN  # noqa: E402
from sloped.scale import SIM_TO_LAYOUT  # noqa: E402
from sloped.track import TrackRun  # noqa: E402

# Layout-scale gravity. See `sloped.scale`: the core simulates at 245.25 world
# units per second squared and the layout is 0.57 of that scale.
GRAVITY = 245.25 * SIM_TO_LAYOUT
# A rolling sphere carries 7/5 of the kinetic energy of a sliding one at the
# same speed, and the same factor appears in how much of a slope it needs.
ROLLING = 5.0 / 7.0

# Thresholds. Each is a number this course has been measured against rather
# than a preference, and each prints its reason when it fires.
#
# A tangent break of more than this is a corner rather than a curve: the
# samples are about 0.35 layout units apart, so 6 degrees is a lateral step of
# 0.037 - an eighth of a marble radius - and anything larger is felt.
TANGENT_BREAK = 6.0
# Degrees of roll per layout unit. The channel is 1.88 across, so 12 deg/unit
# rolls the far wall 0.20 vertically in one unit of travel; at 25 units per
# second that is a wall moving under the marble at 4.1 units per second.
BANK_RATE = 12.0
# A grade break steeper than this throws a marble off the floor rather than
# turning it.
GRADE_BREAK = 8.0
# A floor step of a fifth of a marble radius is a kerb.
FLOOR_STEP = 0.2 * layout.MARBLE_RADIUS


def ride_height(radius: float, bank_deg: float, outward: float, speed: float,
                scale: float = 1.0) -> tuple[float, float, bool]:
    """How high up the channel a marble at `speed` rides through this turn.

    Returns (height above the cradle's lowest point, the outward surface angle
    it needs, whether it runs out of channel). Both heights are in layout units
    in the same frame as `TrackRun.containment`, so they compare directly.

    **This replaces a `hold_speed` that was wrong twice over.** That one took
    `tan(bank + wall)` with the sum clamped at 89 degrees, so a positive bank
    put the argument at the clamp and `tan(89)` made almost every turn look
    able to hold anything - leg1 reported zero tight samples while marbles were
    demonstrably leaving it. And it added the bank to the wall regardless of
    which way the turn went, so a bank rolled the wrong way for its corner read
    as helping.

    The model here is the marble's own equilibrium. A marble going round a turn
    of radius `R` at speed `v` needs `v^2 / R` of horizontal acceleration toward
    the centre. A surface whose outward tangent makes an angle `t` with the
    horizontal supplies `g tan(t)`. So the marble climbs outward until the
    surface is steep enough, and the height it climbs to is read off the
    channel's own profile - walked outward point by point, with the bank added
    to each segment's own angle and its sign taken from which way the corner
    turns.

    `outward` is +1 when the outward side of the turn is the channel's +lateral
    side and -1 when it is the other, so `outward * bank` is the bank's
    contribution on the side the marble is actually pushed toward.
    """
    from sloped.track import channel_profile

    if radius <= 0.0 or radius == float("inf"):
        return 0.0, 0.0, False
    needed = math.degrees(math.atan2(speed * speed / radius, GRAVITY))
    profile = channel_profile(scale)
    # The half of the profile the marble is pushed onto, ordered outward from
    # the cradle's lowest point.
    side = [
        (across * outward, up) for across, up in profile
        if across * outward >= 0.0
    ]
    side.sort(key=lambda point: point[0])
    bank = outward * bank_deg
    for (a0, u0), (a1, u1) in zip(side, side[1:]):
        run = a1 - a0
        if run <= 1e-9:
            continue
        segment = math.degrees(math.atan2(u1 - u0, run))
        # The surface's outward tilt, with the bank rolled into it. A banked
        # channel is already tilted, so the marble needs less of the profile.
        if segment + bank >= needed:
            # It balances somewhere on this segment; take the far end, which is
            # the conservative reading of where it sits.
            return u1 - min(u for _a, u in side), needed, False
    top = max(u for _a, u in side) - min(u for _a, u in side)
    return top, needed, True


def audit(run: TrackRun, speed: float) -> list[dict]:
    path = [tuple(p * SIM_TO_LAYOUT for p in point) for point in run.sim_path]
    arc = [value * SIM_TO_LAYOUT for value in run.sim_arc]
    count = len(path)
    rows: list[dict] = []
    for index in range(count):
        row: dict = {
            "sample": index,
            "pct": round(100.0 * index / max(count - 1, 1), 1),
            "bank_deg": round(math.degrees(run.banks[index]), 2),
            "width": round(run.widths[index], 4),
        }
        if 0 < index < count - 1:
            a, b, c = path[index - 1], path[index], path[index + 1]
            first = [b[axis] - a[axis] for axis in range(3)]
            second = [c[axis] - b[axis] for axis in range(3)]
            len1 = math.sqrt(sum(v * v for v in first)) or 1e-9
            len2 = math.sqrt(sum(v * v for v in second)) or 1e-9
            dot = sum(first[axis] * second[axis] for axis in range(3)) / (len1 * len2)
            row["tangent_break_deg"] = round(
                math.degrees(math.acos(max(-1.0, min(1.0, dot)))), 3
            )
            row["grade_deg"] = round(
                math.degrees(math.asin(max(-1.0, min(1.0, -second[1] / len2)))), 2
            )
            previous_grade = math.degrees(
                math.asin(max(-1.0, min(1.0, -first[1] / len1)))
            )
            row["grade_break_deg"] = round(abs(row["grade_deg"] - previous_grade), 3)
            # Horizontal turn radius through the three points.
            ax, az, bx, bz, cx, cz = a[0], a[2], b[0], b[2], c[0], c[2]
            area = abs((bx - ax) * (cz - az) - (cx - ax) * (bz - az)) / 2.0
            s1 = math.dist((ax, az), (bx, bz))
            s2 = math.dist((bx, bz), (cx, cz))
            s3 = math.dist((ax, az), (cx, cz))
            radius = (s1 * s2 * s3) / (4.0 * area) if area > 1e-9 else float("inf")
            row["radius"] = None if radius == float("inf") else round(radius, 3)
            # Which side of the channel the corner throws the marble onto. The
            # turn's own normal is the horizontal component of the tangent's
            # change; projected on the run's lateral axis it says whether the
            # outward side is +lateral or -lateral, and that is the sign the
            # bank has to be read with.
            lateral = run.frames[index][0]
            turn = [second[0] - first[0] * (len2 / len1),
                    0.0,
                    second[2] - first[2] * (len2 / len1)]
            inward = math.copysign(
                1.0,
                turn[0] * lateral[0] + turn[2] * lateral[2],
            ) if abs(turn[0]) + abs(turn[2]) > 1e-12 else 1.0
            outward = -inward
            row["outward"] = outward
            row["bank_helps"] = bool(outward * row["bank_deg"] > 0.0)
            if radius == float("inf"):
                row["ride_height"] = None
                row["needed_deg"] = None
                row["runs_out"] = False
            else:
                height, needed, over = ride_height(
                    radius, row["bank_deg"], outward, speed, run.scale
                )
                row["ride_height"] = round(height, 4)
                row["needed_deg"] = round(needed, 2)
                row["runs_out"] = over
            span = max(arc[index + 1] - arc[index - 1], 1e-9)
            row["bank_rate"] = round(
                abs(math.degrees(run.banks[index + 1] - run.banks[index - 1])) / span, 3
            )
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=None, help="one run, or all of the chain")
    parser.add_argument("--from", dest="low", type=int, default=None)
    parser.add_argument("--to", dest="high", type=int, default=None)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument(
        "--speed", type=float, default=27.0,
        help="the speed to judge a turn against, in layout units per second",
    )
    options = parser.parse_args(argv)

    names = [options.run] if options.run else list(CHAIN)
    findings: list[str] = []
    report: dict = {"speed": options.speed, "runs": {}}

    for name in names:
        run = TrackRun(name)
        rows = audit(run, options.speed)
        report["runs"][name] = rows
    # A sample is a problem when a marble at the judged speed rides higher than
    # the guard's top, which is `containment` in the same frame. That is the
    # number a guard or a bank has to answer, and it is directly comparable.
        limit = None
        tight = []
        breaks = [r for r in rows if r.get("tangent_break_deg", 0.0) > TANGENT_BREAK]
        rolls = [r for r in rows if r.get("bank_rate", 0.0) > BANK_RATE]
        grades = [r for r in rows if r.get("grade_break_deg", 0.0) > GRADE_BREAK]
        limit = run.containment * SIM_TO_LAYOUT
        floor = -layout.FLOOR_Y * run.scale
        tight = [
            r for r in rows
            if r.get("ride_height") is not None
            and (r["runs_out"] or r["ride_height"] + floor > limit)
        ]
        print(f"=== {name}: {len(rows)} samples, "
              f"{run.sim_arc[-1] * SIM_TO_LAYOUT:.2f} layout units, containment "
              f"{limit:.3f} ===")
        print(f"  samples where {options.speed:.0f} units/s rides over the guard: "
              f"{len(tight)}")
        wrong = [r for r in rows
                 if r.get("bank_helps") is False and abs(r["bank_deg"]) > 6.0]
        if wrong:
            print(f"  samples whose bank is rolled the wrong way for their "
                  f"corner: {len(wrong)}")
        print(f"  tangent breaks over {TANGENT_BREAK} deg: {len(breaks)}")
        print(f"  bank rate over {BANK_RATE} deg/unit: {len(rolls)}")
        print(f"  grade breaks over {GRADE_BREAK} deg: {len(grades)}")
        if tight:
            worst = max(tight, key=lambda r: r["ride_height"])
            bands: dict[str, int] = {}
            for r in tight:
                key = f"{10 * (r['sample'] * 10 // len(rows))}..{10 * (r['sample'] * 10 // len(rows)) + 9}%"
                bands[key] = bands.get(key, 0) + 1
            print(f"    worst at sample {worst['sample']} ({worst['pct']}%): radius "
                  f"{worst['radius']}, bank {worst['bank_deg']:+.1f} "
                  f"({'helps' if worst['bank_helps'] else 'WRONG WAY'}), needs "
                  f"{worst['needed_deg']:.1f} deg of surface, rides to "
                  f"{worst['ride_height'] + floor:.3f} against {limit:.3f}")
            print("    bands: " + ", ".join(f"{k} x{v}" for k, v in sorted(bands.items())))
            findings.append(
                f"{name}: {len(tight)} samples ride over the guard at "
                f"{options.speed:.0f} units/s, worst {worst['ride_height'] + floor:.3f} "
                f"against {limit:.3f} at sample {worst['sample']}"
            )
        for label, group, key in (
            ("tangent break", breaks, "tangent_break_deg"),
            ("bank rate", rolls, "bank_rate"),
            ("grade break", grades, "grade_break_deg"),
        ):
            if group:
                worst = max(group, key=lambda r: r[key])
                print(f"    worst {label} {worst[key]} at sample {worst['sample']}")
                findings.append(
                    f"{name}: {len(group)} samples exceed the {label} threshold, "
                    f"worst {worst[key]} at sample {worst['sample']}"
                )
        if options.low is not None:
            print()
            print("  sample    %  |  radius | needs | rides |  bank  | way | rate "
                  "| tangent")
            for r in rows:
                if r["sample"] < options.low or r["sample"] > (options.high or 10 ** 9):
                    continue
                rides = r.get("ride_height")
                print(
                    f"  {r['sample']:6} {r['pct']:5.1f} | "
                    f"{'    -' if r.get('radius') is None else format(r['radius'], '7.2f')} | "
                    f"{'    -' if r.get('needed_deg') is None else format(r['needed_deg'], '5.1f')} | "
                    f"{'    -' if rides is None else format(rides + floor, '5.3f')}"
                    f"{'*' if r.get('runs_out') else ' '}| "
                    f"{r['bank_deg']:+6.1f} | "
                    f"{'  + ' if r.get('bank_helps') else '  - '} | "
                    f"{r.get('bank_rate', 0.0):4.1f} | "
                    f"{r.get('tangent_break_deg', 0.0):7.2f}"
                )
        print()

    # --- the joins between consecutive runs -------------------------------
    print("=== joins ===")
    for first, second in zip(CHAIN, CHAIN[1:]):
        a, b = TrackRun(first), TrackRun(second)
        end = [v * SIM_TO_LAYOUT for v in a.sim_path[-1]]
        begin = [v * SIM_TO_LAYOUT for v in b.sim_path[0]]
        gap = math.dist(end, begin)
        step = begin[1] - end[1]
        bank_step = abs(math.degrees(b.banks[0] - a.banks[-1]))
        print(f"  {first} -> {second}: centreline gap {gap:.4f}, floor step "
              f"{step:+.4f}, bank step {bank_step:.2f} deg, width "
              f"{a.widths[-1]:.3f} -> {b.widths[0]:.3f}")
        if abs(step) > FLOOR_STEP:
            findings.append(
                f"{first} -> {second}: a floor step of {step:+.4f} is a kerb"
            )
        if bank_step > 4.0:
            findings.append(
                f"{first} -> {second}: the bank jumps {bank_step:.1f} deg at the join"
            )
    report["findings"] = findings

    print()
    if findings:
        print(f"FINDINGS ({len(findings)}):")
        for finding in findings:
            print(f"  - {finding}")
    else:
        print("no findings")

    if options.json:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {options.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

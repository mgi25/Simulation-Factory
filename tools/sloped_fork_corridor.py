"""The fork transition as a corridor a marble centre can occupy, not as meshes.

Section 4 of the V1.13 brief: derive the fork opening from the **actual marble
corridor**. Every previous account of this junction - `sloped.joins`,
`sloped.stations.ForkRidge`, `tools/sloped_fork_section.py` - reports where
*surfaces* are. A surface is not a corridor: a 5%-height guard is a surface a
marble rolls straight over, and the outside *corner* of a full-height guard
blocks a marble centre a whole radius before the guard's own face does.

So this reports, at every station through `leg3[..]` and `orange_lead[..]`:

* the run's own frame - centreline, heading, **signed bank**, lateral slope and
  both running edges, in world coordinates;
* a vertical section of the assembled collider, by owner, exactly as
  `tools/sloped_fork_section.py` fires it;
* and then the thing that decides the outcome: the **centre envelope**, the
  lowest height a marble *centre* can sit at each `across`. It is the upper
  envelope of radius-r circles centred on every surface sample - the Minkowski
  dilation of the section by the marble - so a corner obstructs a radius early,
  a hole narrower than a diameter is bridged with a measured sag, and a low lip
  is simply passable.

The envelope is the surface the marble's **centre** rides, so a point mass
rolling on it is the marble. That is what makes it the right curve to read
laterally: its minimum is the line a marble settles on, and its height above
that minimum is the lateral energy a marble needs to be at that `across` at
all. So the readings are energy corridors rather than a clearance:

    floor       where the envelope is lowest - the line a marble settles on
    band(h)     the width of the connected interval about that minimum where
                the envelope stays within `h` of it, for h = 0.10, 0.25, 0.50
    hole        the widest run of rays that hit nothing, against a diameter
    climb       the envelope's rise between this station and the last one at
                the *same* across, which is the ramp a marble meets head-on

**`seat` is not one of them, and that is a correction.** A first version of this
tool called a marble "running" where the envelope stood less than 0.06 above the
floor under it, and reported that only the western 1.20 of leg3's 3.21-wide
channel was runnable at the fork. That reading is arithmetic, not geometry: a
marble resting on a plane inclined at `t` has its centre `r / cos t` above the
surface vertically below it, so on leg3's 26-degree bank the seat is
`0.5 * (1 / cos 26 - 1)` = **0.0563** everywhere, obstruction or not. The
threshold was measuring the bank.

    python tools/sloped_fork_corridor.py --run leg3 --first 78 --last 106

`across` is horizontal distance along the run's *unrolled* side axis, positive
east, and `rise` is height above the run's cradle bottom measured straight up -
the frame `sloped_fork_section` and `sloped_fork_trace` already use, so their
rows line up with these.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.world import MarbleWorld
from sloped import joins, layout
from sloped.course import sloped_course

DROP = 12.0          # simulation units above the station the rays start from
REACH = 30.0         # and how far down they look

# The lateral energy heights the corridor is measured at, in simulation units.
#
# Read as a height a marble's centre has to gain to be that far across. 0.10 is
# a marble drifting; 0.25 is about what 8 wu/s of lateral speed buys
# (v^2 / 2g with g = 9.81 * LAYOUT_TO_SIM); 0.50 is a diameter's worth of climb
# and about the top of a full-height guard above the cradle edge.
BANDS = (0.10, 0.25, 0.50)

GLYPH = {
    "leg3": "3",
    "orange_lead": "O",
    "orange": "o",
    "fork": "^",
    "fork_end": "W",
    "blue_lead": "B",
    "blue": "b",
    "merge": "m",
    "final": "f",
    "": ".",
}


def side_axis(run, index: int):
    """The run's horizontal side axis - lateral with the roll taken out."""
    forward = run.tangents[index]
    side = (forward[2], 0.0, -forward[0])
    length = math.hypot(side[0], side[2])
    return (side[0] / length, 0.0, side[2] / length) if length > 1e-9 else (1.0, 0.0, 0.0)


def section_rays(world: MarbleWorld, run, index: int, lo: float, hi: float, step: float):
    """One vertical section: (across, owner, rise) per ray, floor-relative."""
    side = side_axis(run, index)
    centre = run.sim_path[index]
    # The cradle bottom, which is the centreline walked down the frame's own
    # up by `floor_offset` - a **negative** number. `centre[1] - floor_offset`
    # is 0.456 simulation units the wrong way and was the reference both this
    # and `sloped_fork_corridor` used, so every `rise` either printed was 0.912
    # too low. `sloped_fork_trace` has always had it right; the three agree now.
    _lateral, up, _forward = run.frames[index]
    floor = centre[1] + up[1] * run.floor_offset
    count = int(round((hi - lo) / step)) + 1
    offsets = [lo + step * n for n in range(count)]
    starts, ends = [], []
    for across in offsets:
        base = tuple(centre[axis] + side[axis] * across for axis in range(3))
        starts.append((base[0], base[1] + DROP, base[2]))
        ends.append((base[0], base[1] + DROP - REACH, base[2]))
    rows = []
    for across, (body, _fraction, point) in zip(offsets, world.ray_batch(starts, ends)):
        rows.append(
            {
                "across": across,
                "owner": world.owner_of(body) if body >= 0 else "",
                "rise": None if body < 0 else point[1] - floor,
            }
        )
    return rows


def centre_envelope(rows: Sequence[dict], radius: float = MARBLE_RADIUS) -> list[dict]:
    """The lowest a marble centre can sit at each `across`, and its seat.

    The envelope is `max over surface samples p of p.rise + sqrt(r^2 - dx^2)`
    for `|dx| < r`, which is the boundary of the section dilated by the marble.
    Sampled at the ray offsets, so a row lines up with its own ray.

    `seat` is the envelope minus the rise directly under it, and it is the
    reading section 5 of the brief asks for: a marble whose seat is zero is on
    the floor, and one whose seat is 0.3 is standing on something's corner a
    radius away from where the mesh appears to be.

    A ray that hit nothing contributes no circle, so a hole is *bridged* by its
    two edges when it is narrower than a diameter and is a fall when it is not.
    `seat` is None where nothing is under the marble at all.
    """
    hits = [(row["across"], row["rise"]) for row in rows if row["rise"] is not None]
    out: list[dict] = []
    for row in rows:
        across = row["across"]
        best = None
        for point_across, point_rise in hits:
            offset = across - point_across
            if abs(offset) >= radius:
                continue
            height = point_rise + math.sqrt(max(radius * radius - offset * offset, 0.0))
            if best is None or height > best:
                best = height
        floor = row["rise"]
        seat = None if (best is None or floor is None) else best - (floor + radius)
        out.append(
            {
                "across": round(across, 4),
                "owner": row["owner"],
                "rise": None if floor is None else round(floor, 4),
                "centre": None if best is None else round(best, 4),
                "seat": None if seat is None else round(seat, 4),
            }
        )
    return out


def _spans(flags: Sequence[bool]) -> list[tuple[int, int]]:
    out, start = [], None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            out.append((start, index - 1))
            start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


def describe(
    env: Sequence[dict],
    step: float,
    bands: Sequence[float] = BANDS,
    about: float | None = None,
) -> dict[str, Any]:
    """The energy corridor, the hole and the interior ridges, per station.

    `about` anchors the bands on a chosen `across` rather than on the envelope's
    global minimum, which is what a *transition* needs: through the fork the
    global minimum jumps from leg3's cradle to orange's, and a band measured
    about the jumped-to minimum would report a healthy corridor at the exact
    station a marble bound the other way has nowhere to go. Passing the
    previous station's floor keeps the reading on one corridor.
    """
    heights = [row["centre"] for row in env]
    seen = [(index, value) for index, value in enumerate(heights) if value is not None]
    if not seen:
        return {"floor": None, "floor_height": None, "bands": {}, "hole": None}
    if about is None:
        anchor = min(seen, key=lambda pair: pair[1])[0]
    else:
        # The lowest point of the connected run of envelope containing `about`,
        # so the anchor tracks one corridor rather than jumping to a lower one
        # across a hole.
        start = min(range(len(env)), key=lambda i: abs(env[i]["across"] - about))
        if heights[start] is None:
            nearest = min(seen, key=lambda pair: abs(pair[0] - start))
            start = nearest[0]
        low, high = start, start
        while low > 0 and heights[low - 1] is not None:
            low -= 1
        while high < len(env) - 1 and heights[high + 1] is not None:
            high += 1
        anchor = min(range(low, high + 1), key=lambda i: heights[i])
    base = heights[anchor]

    out_bands: dict[str, Any] = {}
    for height in bands:
        west = anchor
        while west > 0 and heights[west - 1] is not None and heights[west - 1] <= base + height:
            west -= 1
        east = anchor
        while (
            east < len(env) - 1
            and heights[east + 1] is not None
            and heights[east + 1] <= base + height
        ):
            east += 1
        out_bands[format(height, ".2f")] = {
            "width": round((east - west + 1) * step, 3),
            "west": env[west]["across"],
            "east": env[east]["across"],
        }

    holes = _spans([row["rise"] is None for row in env])
    inner = [span for span in holes if span[0] > 0 and span[1] < len(env) - 1]
    worst = max(inner, key=lambda span: span[1] - span[0], default=None)
    # Interior ridges: a local maximum of the envelope with runnable envelope
    # either side, which is a crest a marble has to be lifted over. The crest
    # at the fork is one on purpose; any other is a defect.
    ridges = []
    for index in range(1, len(env) - 1):
        left, here, right = heights[index - 1], heights[index], heights[index + 1]
        if None in (left, here, right):
            continue
        if here >= left and here > right and here - base > 0.02:
            ridges.append([env[index]["across"], round(here - base, 4)])
    return {
        "floor": env[anchor]["across"],
        "floor_height": round(base, 4),
        "bands": out_bands,
        "hole": None if worst is None else round((worst[1] - worst[0] + 1) * step, 3),
        "hole_at": None if worst is None else env[worst[0]]["across"],
        "hole_bridged": (
            None
            if worst is None
            else bool(
                env[worst[0]]["centre"] is not None or env[worst[1]]["centre"] is not None
            )
        ),
        "ridges": ridges[:6],
    }


def frame_of(run, index: int) -> dict[str, Any]:
    """One station's own geometry, in world units: floor, bank, edges, tangent."""
    lateral, up, forward = run.frames[index]
    centre = run.sim_path[index]
    half = layout.CHANNEL_HALF
    west = run.surface_point(index, -half)
    east = run.surface_point(index, half)
    # Lateral slope of the running surface between the two cradle edges, in
    # world terms: the height difference over the horizontal separation. This is
    # the number that says which way a marble on the floor is pulled, and it is
    # not the bank when the width flare and the profile scale differ.
    span = math.hypot(east[0] - west[0], east[2] - west[2])
    return {
        "sample": index,
        "arc": round(run.sim_arc[index], 4),
        "floor_y": round(centre[1] - run.floor_offset, 4),
        "heading_deg": round(run.heading_deg(index), 3),
        "grade_deg": round(-math.degrees(math.asin(max(-1.0, min(1.0, forward[1])))), 3),
        "bank_deg": round(math.degrees(run.banks[index]), 3),
        "lateral_slope": round((east[1] - west[1]) / span, 4) if span > 1e-9 else 0.0,
        "half_width": round(0.5 * run.clear_width * run.widths[index], 4),
        "wall_factor": round(run.wall_factor(index), 4),
        "guard_extra": round(run.guard_extra(index), 4),
        "entry_trim": run.entry_trim_at(index),
        "west_edge": [round(value, 4) for value in west],
        "east_edge": [round(value, 4) for value in east],
        "up": [round(value, 4) for value in up],
        "lateral": [round(value, 4) for value in lateral],
    }


def _cell(value, width: int, places: int) -> str:
    if value is None:
        return "-".rjust(width)
    return format(value, str(width) + "." + str(places) + "f")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", default="leg3")
    parser.add_argument("--first", type=int, default=78)
    parser.add_argument("--last", type=int, default=106)
    parser.add_argument("--every", type=int, default=1)
    parser.add_argument("--lo", type=float, default=-4.0)
    parser.add_argument("--hi", type=float, default=9.0)
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--routes", default="both")
    parser.add_argument("--crest", type=float, default=None)
    parser.add_argument("--station", default=None, help="pan or ridge")
    parser.add_argument(
        "--about",
        type=float,
        default=None,
        help="anchor every band on this across rather than on the envelope's own minimum",
    )
    parser.add_argument("--rows", action="store_true", help="print the per-across envelope")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    if args.crest is not None or args.station is not None:
        import sloped.course as _course

        if args.crest is not None:
            _course.FORK_CREST = args.crest
        if args.station is not None:
            _course.FORK_STATION = args.station

    machine = sloped_course(routes=args.routes)
    world = MarbleWorld(DEFAULT_CONFIG)
    machine.build(world)
    run = machine.runs[args.run]                     # type: ignore[attr-defined]

    print("marble diameter " + format(MARBLE_DIAMETER, ".4f") + ", radius "
          + format(MARBLE_RADIUS, ".4f") + " sim units")
    print(args.run + ": " + str(len(run.sim_path)) + " samples, crest "
          + str(args.crest) + ", bands " + str(BANDS))
    print("smpl    bank     lat  wall   trim |  floor  b0.10        b0.25        "
          "b0.50         hole  climb       | profile")
    print("-" * 118)
    stations = []
    previous_floor = args.about
    previous_env = None
    previous_band = None
    for index in range(args.first, args.last + 1, args.every):
        if not 0 <= index < len(run.sim_path):
            continue
        rows = section_rays(world, run, index, args.lo, args.hi, args.step)
        env = centre_envelope(rows)
        facts = describe(env, args.step, about=previous_floor)
        frame = frame_of(run, index)
        # Section 5's continuity reading: the envelope's rise at the *same*
        # across between two consecutive stations. A marble travels 0.352 sim
        # units of arc a sample here, so a rise of 0.10 is a 16-degree ramp and
        # one of 0.35 is a 45-degree one.
        #
        # Read **only inside the previous station's own corridor**, and that is
        # a correction rather than a refinement. Taken over the whole section it
        # is dominated by the far east, where orange's channel sweeps into and
        # out of leg3's section plane a sample at a time: the envelope there
        # "climbs" a whole unit because a different piece of geometry is under
        # the ray, not because anything a marble can reach went up. Every one of
        # the 1.0-plus readings a first version printed was that.
        climb = None
        climb_at = None
        if previous_env is not None and previous_band is not None:
            for before, now in zip(previous_env, env):
                if before["centre"] is None or now["centre"] is None:
                    continue
                if not previous_band[0] <= now["across"] <= previous_band[1]:
                    continue
                rise = now["centre"] - before["centre"]
                if climb is None or rise > climb:
                    climb, climb_at = rise, now["across"]
        stations.append(
            {
                **frame,
                **facts,
                "climb": None if climb is None else round(climb, 4),
                "climb_at": climb_at,
                "env": env,
            }
        )
        previous_floor = facts["floor"] if args.about is None else args.about
        previous_env = env
        widest = facts["bands"].get(format(max(BANDS), ".2f"))
        previous_band = None if widest is None else (widest["west"], widest["east"])
        bands = facts["bands"]

        def band(key: str) -> str:
            block = bands.get(key)
            if block is None:
                return "     -"
            return (
                _cell(block["width"], 5, 2)
                + "[" + _cell(block["west"], 5, 1)
                + "," + _cell(block["east"], 5, 1) + "]"
            )

        print(
            format(index, ">4d") + " "
            + _cell(frame["bank_deg"], 7, 2) + " "
            + _cell(frame["lateral_slope"], 7, 3) + " "
            + _cell(frame["wall_factor"], 5, 2) + " "
            + _cell(frame["entry_trim"], 6, 2) + " | "
            + _cell(facts["floor"], 6, 2) + " "
            + band("0.10") + " " + band("0.25") + " " + band("0.50") + " "
            + _cell(facts["hole"], 5, 2) + " "
            + _cell(climb, 6, 3) + " at " + _cell(climb_at, 5, 1) + " | "
            + "".join(GLYPH.get(row["owner"], "?") for row in env)
        )
        if args.rows:
            for row in env:
                if row["rise"] is None and row["centre"] is None:
                    continue
                print(
                    "        " + _cell(row["across"], 7, 2) + " "
                    + GLYPH.get(row["owner"], "?")
                    + "  rise " + _cell(row["rise"], 7, 3)
                    + "  centre " + _cell(row["centre"], 7, 3)
                    + "  seat " + _cell(row["seat"], 7, 3)
                )
    world.close()

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "run": args.run,
                    "routes": args.routes,
                    "crest": args.crest,
                    "fork_sample": joins.FORK_SAMPLE,
                    "bands": list(BANDS),
                    "step": args.step,
                    "stations": stations,
                },
                handle,
                indent=1,
            )
            handle.write("\n")
        print("wrote " + args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

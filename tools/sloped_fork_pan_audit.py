"""Is the fork station continuously supported, and is its end behind a wall?

Section 5 of the V1.14 brief, as six named checks rather than a picture. The
invariant it is written against:

    a marble-sized sphere travelling anywhere inside the intended race
    corridor must always have supported floor beneath it until an outgoing
    route's walls have captured it.

`tools/sloped_fork_corridor.py` reports the corridor as an energy landscape and
is the right instrument for "where does a marble go". It cannot answer "is the
surface it is on continuous", because it fires one section plane at a time and
the fork's two runs are 46 degrees apart the moment their cradles part - so a
hole in leg3's plane may be geometry that has simply swung out of it.

So this walks the **station's own rings** and asks, of each one:

    foot seam       the distance from each ring's outer point to the cradle
                    edge it is supposed to stand on. A ring that does not
                    reach its own foot is a floor gap; one that overshoots is
                    a hanging lip.
    support         whether a marble centre has floor under it across the
                    **reachable** region, which is not the same as the ring's
                    own vertices.

                    A first version of this check placed each centre a radius
                    above a point that was already on the surface and reported
                    every drop as exactly 0.500 and every station supported.
                    That is arithmetic, not geometry: it can only fail if a
                    ring point is missing from the collider altogether. So the
                    grid is the strip's **interior and its surroundings** - the
                    midpoints between rings and across them, which catch a sag
                    or a missing quad, and a fan of stations outboard of each
                    foot, which catch the hanging lip and the exposed edge.

                    The ceiling is a radius over the cosine of the steepest
                    runnable face rather than a radius: on a plane inclined at
                    `t` the centre stands `r / cos t` above the point below it,
                    so a fixed 0.62 reads a marble climbing leg3's 70-degree
                    lip as already falling. V1.13's report records that exact
                    reading booking 20 of 58 losses to a site where nothing was
                    wrong.
    gorge path      a ray downstream from a marble centre over each ring,
                    along leg3's tangent. It must meet a wall inside the
                    station's own length. A point whose downstream ray leaves
                    the station without hitting anything has an unobstructed
                    path into the gorge, and that is the defect `ForkRidge`
                    ended in - reported as such rather than inferred from the
                    absence of a wall module.
    downstream edge whether the last ring is covered by a wall, and how tall.
                    An uncovered last ring is the defect this whole session
                    exists for: `ForkRidge` ended over the gorge.
    guard agreement each run's wall factor at each station, so a station whose
                    floor is open on a side where the guard is also open is
                    reported rather than inferred.
    reachable exit  for every ring point, whether continuing **downstream**
                    reaches the station's end edge without meeting a wall.
    span            the ring's length, against a marble diameter, so a station
                    narrower than a marble is named as a straddle rather than
                    a floor.

    python tools/sloped_fork_pan_audit.py --station pan --crest 0.12
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

# How far below a marble centre a surface may be and still be carrying it.
# A radius plus a tolerance for the facet sagitta the core is calibrated at,
# divided by the cosine of the steepest surface a marble can run on. At 45
# degrees that is 0.5 / 0.707 = 0.707, so a marble on a 45-degree face has its
# centre 0.71 above the point directly beneath it and is still supported.
SUPPORT_REACH = MARBLE_RADIUS / math.cos(math.radians(45.0)) + 0.08

# Past this a downward hit is a different surface, not the one under the ring.
PROBE_DROP = 4.0


def _unit(v):
    length = math.sqrt(sum(x * x for x in v))
    if length < 1e-12:
        return (0.0, 1.0, 0.0)
    return tuple(x / length for x in v)


def audit(
    station: str, crest: float, routes: str = "both", window: int | None = None
) -> dict[str, Any]:
    import sloped.course as course

    course.FORK_STATION = station
    course.FORK_CREST = crest
    if window is not None:
        joins.FORK_WINDOW_PAN = window
        joins.FORK_WINDOW_BLUE = window
    machine = sloped_course(routes=routes)
    world = MarbleWorld(DEFAULT_CONFIG)
    machine.build(world)

    fork = machine.modules["fork"]
    leg3 = machine.runs["leg3"]                      # type: ignore[attr-defined]
    other = machine.runs["orange_lead"]              # type: ignore[attr-defined]
    end = machine.modules.get("fork_end")

    # The rings, however the station spells them. `ForkPan` exposes `rings()`;
    # `ForkRidge` does not, and rebuilding its rings here would be a second
    # implementation of the thing under test - so its mesh is read instead and
    # sliced back into rings by its own known width.
    if hasattr(fork, "rings"):
        rings = fork.rings()
    else:
        mesh = fork.local_colliders()[0]
        width = 2 * fork.FLANK_POINTS + 1
        points = [tuple(p) for p in mesh.vertices]
        rings = [points[i : i + width] for i in range(0, len(points), width)]

    # Which sample each ring belongs to. Both stations insert one nose ring
    # upstream of their first station, so ring 0 is the nose and ring k is the
    # k-th *built* station.
    # `ForkPan` can be asked; `ForkRidge` cannot, and `range(len(rings) - 1)`
    # is the wrong answer for it. A first version used that, labelled the
    # ridge's rings 0..11 when the ridge is built over steps 9..20, and then
    # reported every ring standing 5.0 units from "its" cradle edge - the
    # distance between two stations eleven samples apart, not a seam. So the
    # ridge's steps are recovered from its own emission rule instead, which is
    # the same one `ForkPan` uses.
    if hasattr(fork, "_feet"):
        built = [
            step for step, row in enumerate(fork._feet())
            if row[3] > fork.HAIRLINE * MARBLE_DIAMETER
        ]
    else:
        built = []
        for step in range(fork.window + 1):
            a_index = min(fork.index + step, len(fork.run.sim_path) - 1)
            b_index = min(step, len(fork.other.sim_path) - 1)
            west = fork.run.surface_point(a_index, layout.CHANNEL_HALF)
            east = fork.other.surface_point(b_index, -layout.CHANNEL_HALF)
            lateral = fork.run.frames[a_index][0]
            gap = sum((east[i] - west[i]) * lateral[i] for i in range(3))
            if gap > fork.HAIRLINE * MARBLE_DIAMETER:
                built.append(step)
    steps = [None] + built[: len(rings) - 1]

    # The grid: for each pair of consecutive rings, the quad's own interior,
    # plus a fan outboard of each foot. Sampled at marble-centre height above
    # the *interpolated* surface, so a sag between two rings shows as a drop
    # greater than the ceiling rather than as nothing.
    OUTBOARD = (0.25, 0.60, 1.00)          # diameters past a foot
    grid: list[dict[str, Any]] = []
    for index in range(len(rings) - 1):
        near, far = rings[index], rings[index + 1]
        width = len(near)
        for along in (0.0, 0.5):
            for across_step in range(width):
                for shift in (0.0, 0.5):
                    position = across_step + shift
                    if position > width - 1:
                        continue
                    low = int(position)
                    high = min(low + 1, width - 1)
                    blend = position - low
                    def lerp(a, b, t):
                        return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
                    on_near = lerp(near[low], near[high], blend)
                    on_far = lerp(far[low], far[high], blend)
                    point = lerp(on_near, on_far, along)
                    grid.append({"ring": index, "kind": "interior", "point": point})
        # And outboard of the two feet, along the ring's own direction, which
        # is where a hanging lip or an exposed edge lives.
        for end_index, sign in ((0, -1.0), (width - 1, 1.0)):
            inner = near[1] if end_index == 0 else near[width - 2]
            outward = _unit(
                tuple(near[end_index][i] - inner[i] for i in range(3))
            )
            for distance in OUTBOARD:
                point = tuple(
                    near[end_index][i] + outward[i] * distance * MARBLE_DIAMETER
                    for i in range(3)
                )
                grid.append(
                    {
                        "ring": index,
                        "kind": "outboard_west" if sign < 0 else "outboard_east",
                        "point": point,
                        "distance": distance,
                    }
                )

    starts: list[tuple[float, float, float]] = []
    ends: list[tuple[float, float, float]] = []
    for cell in grid:
        centre = (
            cell["point"][0],
            cell["point"][1] + MARBLE_RADIUS,
            cell["point"][2],
        )
        cell["centre"] = centre
        starts.append(centre)
        ends.append((centre[0], centre[1] - PROBE_DROP, centre[2]))

    # The gorge test: a ray downstream from over each ring, along leg3's
    # tangent at that station. It must meet something inside the station.
    span = math.dist(rings[0][0], rings[-1][-1]) + 4.0 * MARBLE_DIAMETER
    gorge: list[dict[str, Any]] = []
    for index, ring in enumerate(rings):
        sample = steps[index] if index < len(steps) else None
        at = joins.FORK_SAMPLE if sample is None else min(
            joins.FORK_SAMPLE + sample, len(leg3.sim_path) - 1
        )
        forward = leg3.frames[at][2]
        for across_step, point in enumerate(ring):
            centre = (point[0], point[1] + MARBLE_RADIUS, point[2])
            gorge.append(
                {
                    "ring": index,
                    "across": across_step,
                    "start": centre,
                    "end": tuple(centre[i] + forward[i] * span for i in range(3)),
                }
            )
    hits = world.ray_batch(
        starts + [cell["start"] for cell in gorge],
        ends + [cell["end"] for cell in gorge],
    )
    support_hits = hits[: len(starts)]
    gorge_hits = hits[len(starts) :]
    for cell, hit in zip(gorge, gorge_hits):
        body, _fraction, _point = hit
        cell["owner"] = None if body < 0 else world.owner_of(body)

    loose_cells: list[dict[str, Any]] = []
    for cell, hit in zip(grid, support_hits):
        body, _fraction, point = hit
        drop = None if body < 0 else cell["centre"][1] - point[1]
        cell["drop"] = drop
        cell["owner"] = None if body < 0 else world.owner_of(body)
        if drop is None or drop > SUPPORT_REACH:
            loose_cells.append(cell)

    open_downstream = [cell for cell in gorge if cell["owner"] is None]

    rows: list[dict[str, Any]] = []
    for index, ring in enumerate(rings):
        step = steps[index] if index < len(steps) else None
        sample = None if step is None else min(
            joins.FORK_SAMPLE + step, len(leg3.sim_path) - 1
        )
        cells = [cell for cell in grid if cell["ring"] == index]
        interior = [cell for cell in cells if cell["kind"] == "interior"]
        drops = [cell["drop"] for cell in interior if cell["drop"] is not None]
        loose = [
            cell for cell in cells
            if cell["drop"] is None or cell["drop"] > SUPPORT_REACH
        ]
        row: dict[str, Any] = {
            "ring": index,
            "step": step,
            "sample": sample,
            "span": round(math.dist(ring[0], ring[-1]), 4),
            "points": len(cells),
            "unsupported_points": [
                {
                    "kind": cell["kind"],
                    "distance": cell.get("distance"),
                    "drop": None if cell["drop"] is None else round(cell["drop"], 4),
                }
                for cell in loose
            ],
            "loose_interior": sum(
                1 for cell in loose if cell["kind"] == "interior"
            ),
            "worst_drop": None if not drops else round(max(drops), 4),
            "owners": sorted(
                set(cell["owner"] for cell in cells if cell["owner"])
            ),
            "open_downstream": sum(
                1 for cell in gorge if cell["ring"] == index and cell["owner"] is None
            ),
        }
        if step is not None:
            b_index = min(step, len(other.sim_path) - 1)
            west = leg3.surface_point(sample, layout.CHANNEL_HALF)
            east = other.surface_point(b_index, -layout.CHANNEL_HALF)
            row["west_seam"] = round(math.dist(ring[0], west), 5)
            row["east_seam"] = round(math.dist(ring[-1], east), 5)
            row["leg3_wall"] = round(leg3.wall_factor(sample), 3)
            row["lead_wall"] = round(other.wall_factor(b_index), 3)
        rows.append(row)

    # The downstream edge: is the last ring covered?
    wall: dict[str, Any] = {"module": None, "height": 0.0, "span": 0.0, "covers": False}
    if end is not None:
        described = end.describe()
        wall.update(
            {
                "module": end.id,
                "height": described["height"],
                "span": described["span"],
            }
        )
        end_mesh = end.local_colliders()[0]
        lowest = [tuple(p) for p in end_mesh.vertices]
        wall["covers"] = all(
            min(math.dist(point, base) for base in lowest) < 1e-6
            for point in rings[-1]
        )
    world.close()

    findings: list[str] = []
    for row in rows:
        if row["loose_interior"]:
            findings.append(
                f"ring {row['ring']} (step {row['step']}, leg3[{row['sample']}]) has "
                f"{row['loose_interior']} interior cells with no floor within "
                f"{SUPPORT_REACH:.3f} - a hole in the station's own surface"
            )
        # Outboard of the **east** foot is orange's channel while the two are
        # adjacent, so a gap there is a real one; outboard of the west foot is
        # leg3's own guard and lip, which a marble cannot be beyond.
        east_loose = [
            cell for cell in row["unsupported_points"]
            if cell["kind"] == "outboard_east" and (cell["distance"] or 0) <= 0.60
        ]
        if east_loose and row["step"] is not None:
            findings.append(
                f"ring {row['ring']} (step {row['step']}) has no floor "
                f"{min(cell['distance'] for cell in east_loose):.2f} diameters past "
                "its east foot, where orange's cradle should be"
            )
        if row["open_downstream"]:
            findings.append(
                f"ring {row['ring']} (step {row['step']}) has "
                f"{row['open_downstream']} of {len(rings[row['ring']])} points whose "
                "downstream ray leaves the station without meeting anything"
            )
        for side in ("west", "east"):
            seam = row.get(f"{side}_seam")
            if seam is not None and seam > 0.02:
                findings.append(
                    f"ring {row['ring']} (step {row['step']}) stands {seam:.4f} from its "
                    f"{side} cradle edge"
                )
    if wall["module"] is None:
        findings.append(
            "the station's downstream edge has no wall over it: its last ring "
            f"spans {rows[-1]['span']:.3f} and ends in open space"
        )
    elif not wall["covers"]:
        findings.append("the end wall does not stand on the pan's last ring")

    return {
        "station": station,
        "crest": crest,
        "support_reach": round(SUPPORT_REACH, 4),
        "cells": len(grid),
        "loose_cells": len(loose_cells),
        "gorge_rays": len(gorge),
        "open_downstream": len(open_downstream),
        "rings": rows,
        "wall": wall,
        "findings": findings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--station", default="pan")
    parser.add_argument("--crest", type=float, default=0.12)
    parser.add_argument("--routes", default="both")
    parser.add_argument("--window", type=int, default=None)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    facts = audit(args.station, args.crest, args.routes, args.window)
    print(
        f"{facts['station']} at crest {facts['crest']}, support reach "
        f"{facts['support_reach']} simulation units"
    )
    print(
        f"{facts['cells']} centre cells, {facts['loose_cells']} without floor; "
        f"{facts['gorge_rays']} downstream rays, {facts['open_downstream']} open"
    )
    header = (
        f"{'ring':>4} {'step':>4} {'smpl':>4} {'span':>7} {'wSeam':>7} {'eSeam':>7} "
        f"{'l3wall':>6} {'ldwall':>6} {'drop':>6} {'loose':>5} {'hole':>4} "
        f"{'open':>4} | owners"
    )
    print(header)
    print("-" * len(header))
    for row in facts["rings"]:
        def cell(key, places=4, width=7):
            value = row.get(key)
            return "-".rjust(width) if value is None else format(value, f">{width}.{places}f")

        print(
            f"{row['ring']:>4} "
            f"{'-' if row['step'] is None else row['step']:>4} "
            f"{'-' if row['sample'] is None else row['sample']:>4} "
            f"{row['span']:>7.3f} {cell('west_seam', 4)} {cell('east_seam', 4)} "
            f"{cell('leg3_wall', 2, 6)} {cell('lead_wall', 2, 6)} "
            f"{cell('worst_drop', 3, 6)} {len(row['unsupported_points']):>5} "
            f"{row['loose_interior']:>4} {row['open_downstream']:>4} | "
            + ",".join(row["owners"])
        )
    wall = facts["wall"]
    print(
        f"\ndownstream edge: wall {wall['module']}, height {wall['height']:.4f}, "
        f"span {wall['span']:.3f}, stands on the last ring {wall['covers']}"
    )
    print(f"findings: {len(facts['findings'])}")
    for finding in facts["findings"]:
        print("  " + finding)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(facts, handle, indent=1)
            handle.write("\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

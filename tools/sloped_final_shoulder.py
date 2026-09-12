"""What surfaces exist around the sprint's first fifteen samples, layer by layer.

Section 6 of the V1.15 brief: inspect the running surface rather than the
centreline, and inspect the shoulder outside the nominal channel as well,
because orange enters the final section from outside it.

The reading is a **layer walk**: a downward ray from well above each grid point,
then another from just under whatever it hit, and so on, so the roof, the rim,
the rail top, the shoulder floor and the cradle are all reported separately
instead of the roof hiding everything under it. Every height is in simulation
units relative to the sprint's own cradle bottom at that `along`, which is the
height a marble at rest on the centreline would measure from.

    python tools/sloped_final_shoulder.py --across -4.6 4.6 --step 0.2

`along` is measured from `final[0]`'s centreline surface point along the
sprint's horizontal heading, so `along = 0.3259 * n` is the sprint's sample `n`.
`across` is horizontal and positive east, the side orange arrives from.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG
from marble3d.units import MARBLE_DIAMETER, MARBLE_RADIUS
from marble3d.world import MarbleWorld

from sloped.course import sloped_course

REACH = 60.0
LAYERS = 6
# How far under a hit the next ray starts. Small enough not to step through a
# thin shell, large enough that the same triangle is not found twice.
SKIN = 0.01


def frame(final):
    """(origin, forward, side) - horizontal axes anchored on `final[0]`."""
    origin = final.surface_point(0, 0.0)
    ahead = final.sim_path[1]
    behind = final.sim_path[0]
    forward = (ahead[0] - behind[0], 0.0, ahead[2] - behind[2])
    length = math.hypot(forward[0], forward[2])
    forward = (forward[0] / length, 0.0, forward[2] / length)
    side = (forward[2], 0.0, -forward[0])
    return origin, forward, side


def world_point(origin, forward, side, along: float, across: float, rise: float):
    return tuple(
        origin[axis] + forward[axis] * along + side[axis] * across + (0.0, rise, 0.0)[axis]
        for axis in range(3)
    )


def datum(final, along: float) -> float:
    """The sprint's own cradle-bottom world height at one `along`, interpolated.

    The sprint is all but straight, so the sample whose surface point projects
    nearest this `along` is found by dividing rather than by searching, and the
    two neighbours are blended.
    """
    spacing = math.dist(final.sim_path[0], final.sim_path[1])
    position = along / spacing
    low = max(0, min(len(final.sim_path) - 2, int(math.floor(position))))
    blend = position - low
    first = final.surface_point(low, 0.0)[1]
    second = final.surface_point(low + 1, 0.0)[1]
    return first + (second - first) * blend


def layer_walk(world, start, floor_y: float):
    """Every surface under one point, top first, as (height, owner)."""
    out = []
    y = start[1]
    for _ in range(LAYERS):
        if y <= floor_y:
            break
        hits = world.ray_batch([(start[0], y, start[2])], [(start[0], floor_y, start[2])])
        body, _fraction, point = hits[0]
        if body < 0:
            break
        out.append((point[1], world.owner_of(body)))
        y = point[1] - SKIN
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--along", type=float, nargs=2, default=(-4.4, 7.0))
    parser.add_argument("--across", type=float, nargs=2, default=(-5.0, 5.0))
    parser.add_argument("--step", type=float, default=0.2)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    machine = sloped_course(routes="both")
    world = MarbleWorld(DEFAULT_CONFIG)
    machine.build(world)
    final = machine.runs["final"]                     # type: ignore[attr-defined]
    origin, forward, side = frame(final)
    spacing = math.dist(final.sim_path[0], final.sim_path[1])

    alongs = []
    value = args.along[0]
    while value <= args.along[1] + 1e-9:
        alongs.append(round(value, 4))
        value += args.step
    acrosses = []
    value = args.across[0]
    while value <= args.across[1] + 1e-9:
        acrosses.append(round(value, 4))
        value += args.step

    grid = {}
    for along in alongs:
        base = datum(final, along)
        for across in acrosses:
            start = world_point(origin, forward, side, along, across, 8.0)
            layers = layer_walk(world, start, base - 6.0)
            grid[(along, across)] = [
                (round(height - base, 4), owner) for height, owner in layers
            ]

    print(f"sprint sample spacing {spacing:.4f}, so sample n is along {spacing:.4f} * n")
    print("heights are simulation units above the sprint's cradle bottom at the same along")
    print()

    # The floor a marble rides: the highest layer that has a marble's worth of
    # clear air above it, or the topmost layer when nothing is over it.
    def floor_of(layers):
        for index, (height, owner) in enumerate(layers):
            if index == 0:
                return height, owner
        return None, None

    def walkable(layers):
        """The surface a marble could stand on, skipping anything it fits under."""
        best = None
        for index, (height, owner) in enumerate(layers):
            if index and layers[index - 1][0] - height < MARBLE_DIAMETER:
                continue
            best = (height, owner)
            break
        return best or (None, None)

    print("=" * 96)
    print("the walkable surface, in simulation units above the local cradle bottom")
    print("=" * 96)
    header = "  along  sample |" + "".join(f"{a:>7.1f}" for a in acrosses)
    print(header)
    for along in alongs:
        cells = []
        for across in acrosses:
            height, _owner = walkable(grid[(along, across)])
            cells.append("      ." if height is None else f"{height:>7.2f}")
        print(f"{along:>7.2f}{along / spacing:>8.1f} |" + "".join(cells))
    print()
    print("=" * 96)
    print("who owns it")
    print("=" * 96)
    codes = {"final": "F", "merge": "M", "merge_lead": "L", "blue": "B", "orange": "O",
             "orange_lead": "R", "finish": "X", "leg3": "3", "blue_lead": "b"}
    print(header)
    for along in alongs:
        cells = []
        for across in acrosses:
            _height, owner = walkable(grid[(along, across)])
            cells.append("      ." if owner is None else f"{codes.get(owner, owner[:1]):>7}")
        print(f"{along:>7.2f}{along / spacing:>8.1f} |" + "".join(cells))

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "spacing": spacing,
                    "alongs": alongs,
                    "acrosses": acrosses,
                    "grid": {f"{a}|{x}": v for (a, x), v in grid.items()},
                },
                handle,
                indent=1,
            )
        print(f"\nwrote {args.out}")
    world.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

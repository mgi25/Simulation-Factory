"""The fork's cross-section, as a marble under gravity actually meets it.

The split's whole argument is written in `sloped.joins` and
`sloped.stations.ForkRidge` in each channel's *own* frame - profile units,
cradle edges, `surface_point`. A marble does not run in either frame. It runs
in gravity's, and what decides whether it crosses east is the shape of a
**vertical** section through the assembled colliders: where the floor is, where
it stops being floor, whether there is a step up or a hole down between leg3's
cradle and orange's.

So this fires a fan of vertical rays across the combined channel at each sample
through the fork window and reports what they hit and how high - by owner, so a
hit on leg3's lip, on the ridge, on orange's lead and on nothing are four
different answers rather than one number.

    python tools/sloped_fork_section.py --steps -4 30 --out docs/validation/...

Read the columns as a profile: `across` is horizontal distance from leg3's
centreline along its own (unrolled) side axis, positive east toward orange, and
`rise` is the surface height above leg3's cradle bottom at that sample,
measured straight up. A marble's centre rides `MARBLE_RADIUS` above the
surface it rests on.
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

from sloped import joins
from sloped.course import sloped_course

DROP = 12.0          # simulation units above the station the rays start from
REACH = 26.0         # and how far down they look

# Short names, so a profile row fits on a line.
GLYPH = {
    "leg3": "3",
    "orange_lead": "O",
    "orange": "o",
    "fork": "^",
    "blue_lead": "B",
    "blue": "b",
    "": ".",
}


def _side_axis(run, index: int):
    """leg3's horizontal side axis - the frame's lateral with the roll taken
    out, so `across` is a horizontal distance and the section is a section a
    falling marble sees rather than one in the banked frame."""
    forward = run.tangents[index]
    side = (forward[2], 0.0, -forward[0])
    length = math.hypot(side[0], side[2])
    return (side[0] / length, 0.0, side[2] / length) if length > 1e-9 else (1.0, 0.0, 0.0)


def section_at(world: MarbleWorld, run, index: int, lo: float, hi: float, step: float):
    """One vertical section, as a list of samples across it."""
    side = _side_axis(run, index)
    centre = run.sim_path[index]
    floor = centre[1] - run.floor_offset
    offsets = [lo + step * n for n in range(int(round((hi - lo) / step)) + 1)]
    starts, ends = [], []
    for across in offsets:
        base = tuple(centre[axis] + side[axis] * across for axis in range(3))
        starts.append((base[0], base[1] + DROP, base[2]))
        ends.append((base[0], base[1] + DROP - REACH, base[2]))
    rows = []
    for across, (body, _fraction, point) in zip(offsets, world.ray_batch(starts, ends)):
        owner = world.owner_of(body) if body >= 0 else ""
        rows.append(
            {
                "across": round(across, 3),
                "owner": owner,
                "rise": None if body < 0 else round(point[1] - floor, 4),
            }
        )
    return rows


def _profile_line(rows: Sequence[dict]) -> str:
    return "".join(GLYPH.get(row["owner"], "?") for row in rows)


def describe(rows: Sequence[dict]) -> dict[str, Any]:
    """The three things a section has to answer, from its own samples.

    * **the void** - the widest run of rays that hit nothing at all, which is
      the hole a marble crossing east falls into;
    * **the step** - the largest jump in surface height between two adjacent
      rays that are 0.05 apart, which is the kerb it trips on;
    * **the reach** - how far east the surface stays inside a marble radius of
      leg3's floor level, which is how far a marble can cross while still
      rolling rather than falling or climbing.
    """
    void_run = best_void = 0
    void_at = None
    for index, row in enumerate(rows):
        if row["rise"] is None:
            void_run += 1
            if void_run > best_void:
                best_void, void_at = void_run, rows[index - void_run + 1]["across"]
        else:
            void_run = 0
    worst_step = 0.0
    step_at = None
    for a, b in zip(rows, rows[1:]):
        if a["rise"] is None or b["rise"] is None:
            continue
        jump = abs(b["rise"] - a["rise"])
        if jump > worst_step:
            worst_step, step_at = jump, b["across"]
    spacing = rows[1]["across"] - rows[0]["across"] if len(rows) > 1 else 0.05
    return {
        "void_width": round(best_void * spacing, 3),
        "void_at": void_at,
        "worst_step": round(worst_step, 4),
        "step_at": step_at,
        "owners": sorted({row["owner"] for row in rows if row["owner"]}),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--first", type=int, default=-4, help="steps past the fork")
    parser.add_argument("--last", type=int, default=30)
    parser.add_argument("--every", type=int, default=2)
    parser.add_argument("--lo", type=float, default=-4.0)
    parser.add_argument("--hi", type=float, default=9.0)
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    machine = sloped_course(routes="both")
    world = MarbleWorld(DEFAULT_CONFIG)
    machine.build(world)
    leg3 = machine.runs["leg3"]                      # type: ignore[attr-defined]

    print(f"marble diameter {MARBLE_DIAMETER:.4f}, radius {MARBLE_RADIUS:.4f} sim units")
    print(f"leg3 half width at the fork {0.5 * leg3.clear_width * leg3.widths[joins.FORK_SAMPLE]:.4f}")
    print(f"across from {args.lo} to {args.hi} at {args.step}; glyphs {GLYPH}")
    sections = []
    for step in range(args.first, args.last + 1, args.every):
        index = joins.FORK_SAMPLE + step
        if not 0 <= index < len(leg3.sim_path):
            continue
        rows = section_at(world, leg3, index, args.lo, args.hi, args.step)
        facts = describe(rows)
        sections.append({"step": step, "sample": index, "rows": rows, **facts})
        void_at = "    -" if facts["void_at"] is None else f"{facts['void_at']:>5.2f}"
        step_at = "    -" if facts["step_at"] is None else f"{facts['step_at']:>5.2f}"
        print(
            f"+{step:>3} [{index:>3}]  void {facts['void_width']:>5.2f} at {void_at}"
            f"  step {facts['worst_step']:>6.3f} at {step_at}"
            f"  |{_profile_line(rows)}|"
        )
    world.close()

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"fork_sample": joins.FORK_SAMPLE, "sections": sections}, handle, indent=1)
            handle.write("\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

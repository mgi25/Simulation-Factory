"""Export the start module's own geometry, so the render can draw what runs.

Section 4 of the V1.17 brief: *do not hard-code another guessed start layout*.
The renderer should consume the same authoritative values `ShuffleFloor` does.

So this reads the **built** module - its origin, its frame, its derived heights
and the half-extents of every kinematic part it emits - and writes them as
JSON. Nothing in `sloped/` is touched and nothing is recomputed, so a change to
the physics start moves this file with it and
`tests/test_sloped_start_render.py` fails if the render is left behind.

    python tools/sloped_start_contract.py --out output/sloped_race_v1/start_contract.json

## Units

**Layout units throughout**, which is the frame the Godot course is authored
in. The module's own local constants are already layout - `R_WALL` 2.7 is 2.7
layout, and `clearances.free_radial_travel` 2.415 is `R_WALL - MARBLE_RADIUS`
in the same units.

**The one exception is `describe()["bay_pitch"]`**, which is
`to_sim(layout.BAY_PITCH)` = 1.105263 while every other number in that
dictionary is layout. That is what made the start look like it had a 1.75x
pitch error when the render's own 0.63 was right all along: 0.63 layout *is*
1.105263 simulation, and both come from `layout.BAY_PITCH`. This file reports
`bay_pitch` 0.63 and `bay_pitch_sim` 1.105263 beside it so the two can never be
confused again.

## The moving parts are played, not reimplemented

The eight gate paddles, the four rotor blades and the eighteen floor slats are
kinematic, and `marble3d.replay` already records a transform per actuator per
frame - thirty of them for the start. The renderer builds a box per part at the
size given here and sets its transform from the replay, exactly as it does for
the marbles. There is therefore no release law, no mixing law and no trapdoor
law in the renderer, and nothing for a future physics change to leave behind.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from sloped import layout
from sloped.course import sloped_course
from sloped.scale import SIM_TO_LAYOUT


def actuator_parts(module) -> dict[str, dict[str, Any]]:
    """Every kinematic part the module emits, by name, as a box in layout units.

    Read straight off `local_actuators()` rather than off the built world, and
    that is a correction this file made to itself: a world body's AABB is the
    *axis-aligned* extent of a box that is usually rotated, so the eighteen
    floor slats came back as nine different widths from 1.74 to 3.70 when they
    are nine widths at one thickness lying at nine different angles.
    `half_extents` is the box the solver was actually given.
    """
    out: dict[str, dict[str, Any]] = {}
    for actuator in module.local_actuators():
        half = [round(float(value) * SIM_TO_LAYOUT, 6) for value in actuator.half_extents]
        out[actuator.name] = {
            "half_extents": half,
            "size": [round(value * 2.0, 6) for value in half],
        }
    return out


def families(parts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The parts grouped by name prefix, so the renderer knows what each is."""
    out: dict[str, dict[str, Any]] = {}
    for name, entry in parts.items():
        prefix = "".join(character for character in name if not character.isdigit())
        prefix = prefix.split("_")[0]
        block = out.setdefault(prefix, {"count": 0, "names": [], "sizes": []})
        block["count"] += 1
        block["names"].append(name)
        if entry["size"] not in block["sizes"]:
            block["sizes"].append(entry["size"])
    for block in out.values():
        block["names"].sort()
        block["sizes"].sort()
    return out


def contract(routes: str = "both") -> dict[str, Any]:
    machine = sloped_course(routes=routes)
    start = machine.modules["start"]
    described = start.describe()
    parts = actuator_parts(start)

    return {
        "kind": described["kind"],
        "start_kind": described["start_kind"],
        # Placement. `origin` already carries the lift, and that lift is the
        # whole of the defect this file exists to close: the render drew the
        # start at `layout.NODES["start"]` and the physics stands it `lift`
        # above that, so the field hung in the air.
        "origin": [round(value, 6) for value in start.origin],
        "node": [round(value, 6) for value in layout.NODES["start"]],
        "yaw_deg": round(described["yaw_deg"], 6),
        "lift": round(start.lift, 6),
        "exit_local": [round(value, 6) for value in start.exit_local],
        "bays": layout.BAYS,
        "bay_pitch": round(layout.BAY_PITCH, 6),
        "bay_pitch_sim": round(described["bay_pitch"], 6),
        "bay_x": [
            round((index - (layout.BAYS - 1) * 0.5) * layout.BAY_PITCH, 6)
            for index in range(layout.BAYS)
        ],
        "marble_radius": round(layout.MARBLE_RADIUS, 6),
        "pan": {
            "floor": round(start.pan_floor, 6),
            "back": round(start.PAN_BACK, 6),
            "half": round(start.PAN_HALF, 6),
            "apron_run": round(start.apron_run, 6),
            "apron_grade_deg": round(start.APRON_GRADE, 6),
            "inlet_step": round(start.INLET_STEP, 6),
        },
        "chamber": {
            "centre_z": round(start.CHAMBER_Z, 6),
            "wall_radius": round(start.R_WALL, 6),
            "wall_rise": round(start.WALL_RISE, 6),
            "rim_floor": round(start.rim_floor, 6),
            "inlet_half": round(start.INLET_HALF, 6),
            "inlet_half_deg": round(described["chamber"]["inlet_half_deg"], 6),
        },
        "rotor": {
            "paddles": start.PADDLES,
            "root_radius": round(start.ROOT_R, 6),
            "tip_radius": round(start.TIP_R, 6),
            "height": round(start.PADDLE_HEIGHT, 6),
            "thickness": round(start.PADDLE_THICK, 6),
        },
        "floor": {
            "panels": start.PANELS,
            "pitch": round(start.panel_pitch, 6),
            "thickness": round(start.PANEL_THICK, 6),
            "splits": start.PANEL_SPLITS,
            "top": round(start.rim_floor, 6),
            "opens_at": round(described["floor"]["opens_at"], 6),
        },
        "cone": {
            "half": round(start.CATCH_HALF, 6),
            "throat": round(start.THROAT_R, 6),
            "rim": round(start.dish_edge, 6),
            "lip": round(start.dish_lip, 6),
            "rim_rise": round(start.CONE_RIM_RISE, 6),
            "tilt_deg": round(start.FUNNEL_TILT, 6),
        },
        "chute": {
            "mouth_z": round(start.chute_mouth_z, 6),
            "half": round(start.CHUTE_HALF, 6),
            "wall": round(start.CHUTE_WALL, 6),
            "grade_deg": round(start.CHUTE_GRADE, 6),
            "lip": round(start.dish_lip, 6),
        },
        # What the renderer draws and then drives from the replay.
        "parts": parts,
        "families": families(parts),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--routes", default="both", choices=("blue", "both"))
    parser.add_argument("--out", default="output/sloped_race_v1/start_contract.json")
    args = parser.parse_args(argv)

    data = contract(args.routes)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=1, sort_keys=True)
        handle.write("\n")

    print(f"{data['kind']} at {data['origin']}, yaw {data['yaw_deg']} deg")
    print(f"  lift {data['lift']} above node {data['node']}")
    print(
        f"  {data['bays']} bays at pitch {data['bay_pitch']} layout "
        f"({data['bay_pitch_sim']} simulation) - the same number twice"
    )
    print(
        f"  pan floor {data['pan']['floor']}   chamber r "
        f"{data['chamber']['wall_radius']} floor {data['chamber']['rim_floor']}"
        f"   cone lip {data['cone']['lip']}"
    )
    for name, block in sorted(data["families"].items()):
        print(f"  {name:<8} {block['count']:>3} parts, sizes {block['sizes']}")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

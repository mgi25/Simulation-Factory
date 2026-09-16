"""V30.1: which authored surfaces are in the film, for the premium pass.

Usage:

    python tools/race2_v301_surfaces.py            # V30 control + V30.1
    python tools/race2_v301_surfaces.py --world=v301

**The instrument is `tools/race2_v30_surfaces.py` and it is reused rather than
reimplemented**, because the whole value of a Part W coverage number is that
the two passes were counted the same way. That file writes a temporary marker
profile per world - every material in the family replaced by a flat
`unshaded` colour, fog and glow off, and a *linear* grade at unit white and
unit exposure so a flat albedo round-trips to the file exactly - renders the
ten sampled moments, counts pixels within a tolerance of 12 per channel, and
deletes the marker profile again.

What this file changes is three module constants: the worlds under test, where
the marker frames go, and where the report is written. It deliberately does
not touch the counting.

## What V30.1 adds to the question

V30's audit answers "is this family in a frame". It cannot answer "is this
family in a frame *because the scene built it*", and on this course those come
apart: `environment_stage` silently refuses an element inside its clearance of
the racing line or its keep-out of the camera path, and the V30 profile loses
five of its nine warm floor inlays - two of them from the final sprint's own
footprint - and its whole `sweep` portal that way. The marker render still
showed `lit_hall_warm` at 0.61% of the film, because the four inlays that
survived plus the wall slots are enough to register, so coverage alone never
revealed it.

So the two instruments are complementary and both are needed:
`race2_v301_stage.siting` says what the scene accepts, this says what the lens
sees, and a family passes only if it is authored, accepted and visible.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from tools import race2_v30_surfaces as base  # noqa: E402
from tools.race2_v301_review import WORLDS  # noqa: E402

DOCS = "docs/validation/race2/v301_stage"
FRAMES = "output/race2/v301_stage/marker"

# The three constants the instrument reads out of its own module. Patched
# rather than parameterised because the alternative is a second copy of a
# counting loop whose whole purpose is to be the same counting loop.
base.FRAMES = FRAMES
base.DOCS = DOCS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--world", default="v30,v301")
    parser.add_argument("--godot", default="")
    parser.add_argument("--json", default=os.path.join(DOCS, "surfaces.json"))
    parser.add_argument("--txt", default=os.path.join(DOCS, "surfaces.txt"))
    args = parser.parse_args()

    wanted = args.world.split(",")
    report = {}
    for world, environment in WORLDS:
        if world not in wanted:
            continue
        print(f"  marker {world} ({environment})")
        report[world] = base.measure_world(world, environment, args)

    text = base.render_report(report).replace("V30 SURFACE COVERAGE",
                                              "V30.1 SURFACE COVERAGE")
    print(text)
    os.makedirs(DOCS, exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    with open(args.txt, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(f"wrote {args.json} and {args.txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

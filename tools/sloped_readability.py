"""How readable a camera track is, per cut, and how two tracks compare.

    python tools/sloped_readability.py --seed 5432 --edit v21
    python tools/sloped_readability.py --seed 5432 --edit v21 --against v19

Solves the track (or two) from the committed replay and prints
`sloped.readability`'s table: racer scale on a 1080x1920 frame, how much of the
field is in shot, where the pack sits, and what happens at every cut. With
`--against` it prints the same table twice and the deltas, which is the only
form in which "the racers are bigger" is a claim rather than an impression.

Nothing here simulates, renders or writes a deliverable; it reads the replay
and the course and does arithmetic.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from sloped import cameras as cameras_module
from sloped import readability, sightlines, terrain
from sloped.course import sloped_course

OUT_DIR = os.path.join("output", "sloped_race_v1")


def solve(replay: dict[str, Any], machine, edit: str) -> dict[str, Any]:
    plan = cameras_module.EDITS[edit] if edit else None
    return cameras_module.build_track(replay, machine, fps=60, edit=plan)


def table(rows: Sequence[dict[str, Any]]) -> None:
    print(
        f"    {'cut':11s} {'out':>13s} {'ext':>5s} {'px med':>7s} {'px 10%':>7s} "
        f"{'in frame':>10s} {'cov':>5s} {'lost s':>7s} {'occ %':>6s} {'off ctr':>8s} "
        f"{'step':>6s}"
    )
    cursor = 0.0
    for row in rows:
        span = row["seconds"]
        print(
            f"    {row['cut']:11s} {cursor:5.2f}-{cursor + span:5.2f}s "
            f"{row['extent'] or 0:5.1f} {row['px_median']:7.1f} {row['px_tail']:7.1f} "
            f"{row['in_frame_mean']:5.1f}/{row['in_play']:<4.1f} {row['coverage']:5.2f} "
            f"{row['lost_seconds']:7.2f} {row['occupancy'] * 100.0:6.2f} "
            f"{row['off_centre']:8.3f} {row['camera_step']:6.3f}"
        )
        cursor += span


def compare(before: Sequence[dict[str, Any]], after: Sequence[dict[str, Any]]) -> None:
    old = {row["cut"]: row for row in before}
    print(f"    {'cut':11s} {'px med':>16s} {'in frame':>16s} {'occupancy %':>18s}")
    for row in after:
        was = old.get(row["cut"])
        if was is None:
            print(f"    {row['cut']:11s}  new")
            continue
        print(
            f"    {row['cut']:11s} {was['px_median']:6.1f} -> {row['px_median']:6.1f} "
            f"{was['coverage']:6.2f} -> {row['coverage']:6.2f} "
            f"{was['occupancy'] * 100.0:8.2f} -> {row['occupancy'] * 100.0:6.2f}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--edit", default="v212")
    parser.add_argument("--against", default="", help="a second edit to compare with")
    parser.add_argument("--routes", default="both", choices=("blue", "both"))
    parser.add_argument("--json", default="", help="write the report here")
    parser.add_argument(
        "--sightlines", action="store_true",
        help="also run sloped.sightlines on every cut, which is slow",
    )
    args = parser.parse_args(argv)

    with open(os.path.join(OUT_DIR, f"race_{args.seed}.json"), "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    machine = sloped_course(routes=args.routes)

    track = solve(replay, machine, args.edit)
    rows = readability.readability_report(track, replay)
    print(f"--- {args.edit or 'no edit'} ---")
    table(rows)

    print("  cuts:")
    for row in readability.continuity_report(track, replay):
        print(
            f"    {row['from']:>9s} -> {row['to']:<9s} jump {row['jump']}  "
            f"drift {row['drift']}  shared {row['shared']}  "
            f"swing {row['swing']:5.1f} deg  travel {row['travel']:6.2f}  "
            f"pack {row['left']} -> {row['landed']}  racers {row['in_frame']}"
        )

    problems = readability.check_readability(track, replay)
    problems += cameras_module.check_track(track, replay)
    if args.sightlines:
        cfg = terrain.terrain_config(machine.runs)
        bundle = sightlines.Bundle(
            sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
        )
        for cut in track["cuts"]:
            problems += sightlines.check_shot(
                track, replay, machine, bundle, cut=cut["name"], stride=10
            )
    if problems:
        print("  findings:")
        for problem in problems:
            print(f"    - {problem}")
    else:
        print("  no findings")

    if args.against:
        other = solve(replay, machine, args.against)
        was = readability.readability_report(other, replay)
        print(f"--- {args.against} ---")
        table(was)
        print(f"--- {args.against} -> {args.edit} ---")
        compare(was, rows)

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "edit": args.edit,
                    "cuts": rows,
                    "continuity": readability.continuity_report(track, replay),
                    "problems": problems,
                },
                handle,
                indent=1,
            )
            handle.write("\n")
        print(f"  wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

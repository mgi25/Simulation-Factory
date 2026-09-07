"""The controlled split-entry test section 10 of the brief asks for.

    python tools/sloped_split_test.py
    python tools/sloped_split_test.py --alone --json out.json

Launches marbles into the fork at several lateral positions, several realistic
incoming speeds and optionally several approach angles, and reports the three
failures separately: the fork not sorting a marble onto a branch, the branch
not carrying it, and the merge not passing it. The pass condition is confirmed
completion of **both** BLUE and ORANGE through the merge to the finish.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sloped.splitlab import OFFSETS, SPEEDS, entry_sweep, summarise_sweep  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speeds", type=float, nargs="*", default=list(SPEEDS))
    parser.add_argument("--offsets", type=float, nargs="*", default=list(OFFSETS))
    parser.add_argument(
        "--yaws", type=float, nargs="*", default=[0.0], help="approach angles in degrees"
    )
    parser.add_argument(
        "--alone",
        action="store_true",
        help="one marble per run, so a fork failure is not a neighbour's push",
    )
    parser.add_argument("--duration", type=float, default=14.0)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    outcomes = entry_sweep(
        speeds=args.speeds,
        offsets=args.offsets,
        yaws=args.yaws,
        duration=args.duration,
        together=not args.alone,
    )
    report = summarise_sweep(outcomes)
    report["together"] = not args.alone

    print(
        f"{report['entries']} entries: "
        f"{len(args.speeds)} speeds x {len(args.offsets)} offsets x {len(args.yaws)} yaws"
        + ("" if args.alone else ", launched as a field")
    )
    print(f"sorted to: {report['sorted_to']}, unrouted {report['unrouted']}")
    for route in ("blue", "orange"):
        block = report["routes"][route]
        if block is None:
            print(f"  {route:>6}: no entries - the fork never sorted a marble onto it")
            continue
        print(
            f"  {route:>6}: {block['entries']:3d} entered, "
            f"{block['reached_lobe']:3d} reached the lobe, "
            f"{block['reached_merge']:3d} reached the merge, "
            f"{block['finished']:3d} finished ({block['finished_pct']}%), "
            f"left {block['left']}, stopped {block['stopped']}, "
            f"median {block['median_time']}"
        )
    if report["loss_sites"]:
        print("loss sites, worst first:")
        ranked = sorted(
            report["loss_sites"].items(),
            key=lambda kv: -(kv[1]["left"] + kv[1]["stopped"]),
        )
        for site, counts in ranked[:12]:
            print(f"  {site:>18}  left {counts['left']:3d}  stopped {counts['stopped']:3d}")

    # The per-entry grid, which is what says whether a route is reachable from
    # one corner of the channel only.
    print()
    print("verdict by (speed, offset) - f finished, m merged, l lobe, L left, S stopped:")
    speeds = sorted({o.speed for o in outcomes})
    offsets = sorted({o.offset for o in outcomes})
    print("speed | " + " | ".join(f"{o:+5.2f}" for o in offsets))
    for speed in speeds:
        cells = []
        for offset in offsets:
            found = [o for o in outcomes if o.speed == speed and o.offset == offset]
            if not found:
                cells.append("     ")
                continue
            row = found[0]
            tag = "f" if row.finished else ("m" if row.reached_merge else ("l" if row.reached_lobe else "-"))
            if not row.finished:
                tag += "L" if row.lost_at else ("S" if row.stopped_at else "?")
            route = (row.route or "?")[0]
            cells.append(f"{route}{tag:>3}".rjust(5))
        print(f"{speed:5.0f} | " + " | ".join(cells))

    passed = all(
        report["routes"][r] is not None and report["routes"][r]["finished"] > 0
        for r in ("blue", "orange")
    )
    print()
    print("PASS: both routes carried a marble to the finish" if passed else "FAIL: see above")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        report["entries_detail"] = [o.to_json() for o in outcomes]
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

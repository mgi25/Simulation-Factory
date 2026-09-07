"""The section D test: does blue's tail through the merge still trap anything?

    python tools/sloped_merge_test.py
    python tools/sloped_merge_test.py --alone

Launches marbles down blue's last twenty samples at several lateral positions
and several speeds - deliberately including speeds too low to climb a step -
and reports any resting place that recurs. A trap is a shape, so it shows up as
the *same* coordinates from different entries; scatter is not a trap.

The pass condition is no reproducible resting position and every entry either
finishing or being accounted for.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sloped.splitlab import OFFSETS, merge_sweep  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speeds", type=float, nargs="*", default=[8.0, 12.0, 18.0, 25.0, 35.0])
    parser.add_argument("--offsets", type=float, nargs="*", default=list(OFFSETS))
    parser.add_argument("--alone", action="store_true", help="one marble per run")
    parser.add_argument("--duration", type=float, default=14.0)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    outcomes = merge_sweep(
        speeds=args.speeds,
        offsets=args.offsets,
        duration=args.duration,
        together=not args.alone,
    )
    finished = [o for o in outcomes if o.finished]
    stopped = [o for o in outcomes if o.verdict() == "stopped"]
    left = [o for o in outcomes if o.verdict() == "left"]

    print(
        f"{len(outcomes)} entries: {len(args.speeds)} speeds x {len(args.offsets)} offsets"
        + ("" if args.alone else ", launched as a field")
    )
    print(f"  finished {len(finished)}  stopped {len(stopped)}  left {len(left)}")

    sites = Counter(
        f"{o.stopped_at[0]}[{o.stopped_at[1]}]" for o in stopped if o.stopped_at
    )
    if sites:
        print("  resting places, worst first:")
        for site, count in sites.most_common(8):
            flag = "  <- REPRODUCIBLE" if count > 1 else ""
            print(f"    {site:>16}  {count}{flag}")

    print()
    print("verdict by (speed, offset) - f finished, S stopped, L left:")
    speeds = sorted({o.speed for o in outcomes})
    offsets = sorted({o.offset for o in outcomes})
    print("speed | " + " | ".join(f"{o:+5.2f}" for o in offsets))
    for speed in speeds:
        cells = []
        for offset in offsets:
            found = [o for o in outcomes if o.speed == speed and o.offset == offset]
            if not found:
                cells.append("    -")
                continue
            row = found[0]
            cells.append(
                "    f" if row.finished else ("    S" if row.stopped_at else "    L")
            )
        print(f"{speed:5.1f} | " + " | ".join(cells))

    repeated = [site for site, count in sites.items() if count > 1]
    passed = not repeated
    print()
    if passed:
        print(f"PASS: no reproducible resting trap ({len(finished)}/{len(outcomes)} finished)")
    else:
        print(f"FAIL: {repeated} recur across entries")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "entries": len(outcomes),
                    "finished": len(finished),
                    "stopped": len(stopped),
                    "left": len(left),
                    "resting_places": dict(sites),
                    "reproducible": repeated,
                    "detail": [o.to_json() for o in outcomes],
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

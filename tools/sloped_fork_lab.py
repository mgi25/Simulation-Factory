"""Scan the fork's own parameters against whole races, not against a sweep.

    python tools/sloped_fork_lab.py --seeds 16 --grid guards

The controlled entry sweep in `tools/sloped_split_test.py` launches 28 marbles
at chosen offsets and takes twelve seconds, which makes it the right instrument
for "is orange reachable at all". It is the wrong one for "does the fork work
for a field": it never puts a marble where the hairpin actually delivers one,
and section 5 of the V1.10 brief asks for eight racers in traffic.

So this runs real seeds of the real course with one or more of the fork's
constants overridden, and reports what each configuration does to the route
split, to orange's completion and to the loss sites. Overriding rather than
editing, because the point of a scan is that every row is measured the same way
and the file on disk is only one of them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG

# The knobs a row may set, and where each one lives. A name here is a module
# attribute that `sloped.course` reads at build time, so setting it in a worker
# before the machine is built is the whole of the override.
KNOBS = {
    "guard_window": ("sloped.joins", "FORK_GUARD_WINDOW"),
    "lead_window": ("sloped.joins", "FORK_LEAD_WINDOW"),
    "orange_window": ("sloped.joins", "FORK_WINDOW_ORANGE"),
    "ridge_window": ("sloped.joins", "FORK_WINDOW_BLUE"),
    "pan_window": ("sloped.joins", "FORK_WINDOW_PAN"),
    "mouth_across": ("sloped.joins", "ORANGE_MOUTH_ACROSS"),
    "lead_hold": ("sloped.joins", "ORANGE_LEAD_HOLD"),
    "trim_window": ("sloped.joins", "FORK_TRIM_WINDOW"),
    "trim_skirt": ("sloped.track", "TrackRun.TRIM_SKIRT"),
    "max_flank": ("sloped.stations", "ForkRidge.MAX_FLANK"),
    "ridge_floor": ("sloped.stations", "ForkRidge.CREST_FLOOR"),
    "ridge_slew": ("sloped.stations", "ForkRidge.RISE_SLEW"),
    "nose_back": ("sloped.stations", "ForkRidge.NOSE_BACK"),
    # Which divider stands at the fork - "pan" or "ridge". `ForkPan`'s
    # docstring has the three measurements that falsify the ridge; this is here
    # so every row of every previous scan can still be reproduced.
    "fork_station": ("sloped.course", "FORK_STATION"),
    "pan_cap": ("sloped.stations", "ForkPan.SEPARATOR_CAP"),
    "pan_at": ("sloped.stations", "ForkPan.SEPARATOR_AT"),
    "pan_flank": ("sloped.stations", "ForkPan.MAX_FLANK"),
    "pan_flank_deg": ("sloped.stations", "ForkPan.MAX_FLANK_DEG"),
    "pan_slew": ("sloped.stations", "ForkPan.RISE_SLEW"),
    "wall_height": ("sloped.stations", "ForkPanEnd.HEIGHT"),
    "crest": ("sloped.course", "FORK_CREST"),
    # The merge, because V1.15's defect is downstream of the fork and the same
    # harness has to price it: `merge_window` is the sprint's own guard window,
    # `taper_from` and `taper_to` are where the apron's rim eases in to the
    # channel edge. All three decide whether the west shoulder dead-ends.
    "merge_window": ("sloped.course", "MERGE_GUARD_WINDOW"),
    "taper_from": ("sloped.stations", "MergeCatch.TAPER_FROM"),
    "taper_to": ("sloped.stations", "MergeCatch.TAPER_TO"),
    # Two entries of a spec dict rather than module constants; `_target`
    # handles the `[key]` form so the lead's roll law can be scanned too.
    "lead_ease": ("sloped.joins", "JOIN_SPECS[orange_lead][bank_ease_ends]"),
    "lead_gain": ("sloped.joins", "JOIN_SPECS[orange_lead][bank_gain]"),
    "lead_max": ("sloped.joins", "JOIN_SPECS[orange_lead][bank_max]"),
}


_DEFAULTS: dict[str, Any] = {}


def _target(key: str):
    import importlib

    module_name, attribute = KNOBS[key]
    module = importlib.import_module(module_name)
    if "[" in attribute:
        head, _, rest = attribute.partition("[")
        keys = [part.rstrip("]") for part in rest.split("[")]
        owner = getattr(module, head)
        for step in keys[:-1]:
            owner = owner[step]
        return _Item(owner), keys[-1]
    if "." in attribute:
        owner, field = attribute.split(".")
        return getattr(module, owner), field
    return module, attribute


class _Item:
    """An attribute-shaped view of one mapping, so `_apply` needs one path."""

    def __init__(self, mapping) -> None:
        self._mapping = mapping

    def __getattr__(self, key):
        return self._mapping[key]

    def __setattr__(self, key, value) -> None:
        if key == "_mapping":
            object.__setattr__(self, key, value)
        else:
            self._mapping[key] = value


def _apply(row: dict[str, Any]) -> None:
    """Set **every** knob, to the row's value or back to the shipped one.

    Setting only the keys a row names is what a first version did, and it is
    wrong in exactly the way that is hard to see: `ProcessPoolExecutor` reuses
    its workers, the knobs are module attributes, and a worker that had run a
    row setting `orange_window` carried it into the next row that did not. The
    scan's last three configurations came back byte-identical because they were
    the same configuration - and the one that looked best was the one that had
    inherited another row's override. So the defaults are captured once per
    worker and every knob is written on every job.
    """
    if not _DEFAULTS:
        for key in KNOBS:
            owner, field = _target(key)
            _DEFAULTS[key] = getattr(owner, field)
    for key in KNOBS:
        owner, field = _target(key)
        setattr(owner, field, row.get(key, _DEFAULTS[key]))


def _one(job) -> dict[str, Any]:
    row, seeds, marbles, duration = job
    _apply(row)
    from sloped.course import sloped_course
    from sloped.race import run_race

    machine = sloped_course(routes="both")
    out = []
    for seed in seeds:
        outcome, _replay = run_race(seed, machine, DEFAULT_CONFIG, marbles, duration)
        out.append(outcome.to_json())
    return {"label": row["label"], "races": out}


def summarise(label: str, races: Sequence[dict[str, Any]]) -> dict[str, Any]:
    racers = [racer for race in races for racer in race["racers"]]
    total = len(racers)
    sites: Counter = Counter()
    per_route: dict[str, dict[str, int]] = {}
    for racer in racers:
        route = racer["route"] or "unrouted"
        block = per_route.setdefault(route, {"entries": 0, "finished": 0})
        block["entries"] += 1
        block["finished"] += racer["state"] == "finished"
        if racer["state"] != "finished" and racer["last_touch"]:
            sites[f"{racer['last_touch'][0]}[{racer['last_touch'][1]}]"] += 1
    finished = sum(1 for racer in racers if racer["state"] == "finished")
    return {
        "label": label,
        "racers": total,
        "finish": round(finished / max(total, 1), 4),
        "all_eight": round(
            sum(1 for race in races if race["finished"] == len(race["racers"])) / max(len(races), 1), 4
        ),
        "escape": round(sum(1 for r in racers if r["state"] == "escaped") / max(total, 1), 4),
        "stuck": round(sum(1 for r in racers if r["state"] == "stuck") / max(total, 1), 4),
        "routes": {
            name: {
                "share": round(block["entries"] / max(total, 1), 4),
                "completion": round(block["finished"] / max(block["entries"], 1), 4),
                "entries": block["entries"],
            }
            for name, block in sorted(per_route.items())
        },
        "loss_sites": dict(sites.most_common(10)),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=16)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--chunk", type=int, default=2)
    parser.add_argument(
        "--rows",
        default="",
        help='JSON list of {"label": ..., knob: value} rows; empty means the shipped course alone',
    )
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    rows = json.loads(args.rows) if args.rows else [{"label": "as built"}]
    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    jobs = [
        (row, seeds[index : index + args.chunk], args.marbles, args.duration)
        for row in rows
        for index in range(0, len(seeds), args.chunk)
    ]
    started = time.perf_counter()
    if args.workers <= 1:
        done = [_one(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            done = list(pool.map(_one, jobs))
    by_label: dict[str, list] = {}
    for block in done:
        by_label.setdefault(block["label"], []).extend(block["races"])
    reports = [summarise(row["label"], by_label.get(row["label"], [])) for row in rows]

    print(
        f"{len(rows)} configurations x {len(seeds)} seeds in "
        f"{time.perf_counter() - started:.0f}s"
    )
    header = (
        f"{'configuration':<28} {'finish':>7} {'all8':>6} {'esc':>6} {'stk':>6} | "
        f"{'blue%':>6} {'blue fin':>9} | {'orng%':>6} {'orng fin':>9}"
    )
    print(header)
    print("-" * len(header))
    for report in reports:
        blue = report["routes"].get("blue", {"share": 0.0, "completion": 0.0})
        orange = report["routes"].get("orange", {"share": 0.0, "completion": 0.0})
        print(
            f"{report['label']:<28} {report['finish']:>7.3f} {report['all_eight']:>6.2f} "
            f"{report['escape']:>6.3f} {report['stuck']:>6.3f} | "
            f"{blue['share']:>6.3f} {blue['completion']:>9.3f} | "
            f"{orange['share']:>6.3f} {orange['completion']:>9.3f}"
        )
    print()
    for report in reports:
        print(f"  {report['label']}: {report['loss_sites']}")

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"rows": rows, "reports": reports}, handle, indent=1)
            handle.write("\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Score several candidate start geometries against each other, cheaply.

    python tools/sloped_start_scan.py --seeds 120
    python tools/sloped_start_scan.py --seeds 300 --only v1 stagger-30

Section 6 of the brief asks for exactly this loop: candidate geometry, 200-500
start-only trials, rank/slot statistics, compare, keep or reject, and no video
for any of it. The candidate list is in `CANDIDATES` below and each entry is a
`sloped.startlab.StartPlan` - physical geometry only, so a candidate cannot
score well by cheating.

The number to read is `span`: the gap in mean rank between the strongest and
the weakest of the eight bays at the earliest checkpoint, in places. V1 is
3.615 and a fair start is 0.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sloped.startlab import LAB_CHECKPOINTS, StartPlan, run_trial, summarise  # noqa: E402

# --- the candidates -------------------------------------------------------
#
# Read against the measurement in `docs/sloped_race_v1_start_finding.md`: the
# trough funnels eight marbles onto one line, the queue that forms there is
# ordered by how far each bay had to travel sideways to reach it, and that
# order survives to the finish because the rest of the course is a 3.3-diameter
# channel where everyone runs at the same terminal speed.
#
# So there are two families to try. One shortens the outer bays' trip - a
# longitudinal stagger, which is what a running track does about unequal lane
# lengths. The other scrambles the queue after it forms, with studs placed
# while the field is still one channel-width long instead of eighteen units of
# single file, which is where V1's one row sits.

_BAY_X = (-2.205, -1.575, -0.945, -0.315, 0.315, 0.945, 1.575, 2.205)


def _stagger(gain: float, skew: float = 0.0) -> tuple[float, ...]:
    """A stagger proportional to how far out the bay is, plus an optional skew.

    `gain` is layout units of downstream offset per layout unit of lateral
    offset from the centreline. `skew` tilts the whole line, which is the
    handle on the one asymmetry the measurement shows: bay 0 is two and a half
    places worse than bay 7 even though the bays are symmetric, because the
    trough is yawed 24 degrees and the launch it hands to banks to -18.
    """
    return tuple(gain * abs(x) + skew * x for x in _BAY_X)


def _rows(marks, counts, height, span=0.72):
    """Staggered stud rows in the fan: `counts[i]` studs across at `marks[i]`.

    Alternating counts put row i's studs in row i-1's gaps, so a marble that
    misses one meets the next off-centre. `span` keeps the outermost stud
    inside the trough wall, where a marble can actually reach it.
    """
    out = []
    for at, count in zip(marks, counts):
        for pin in range(count):
            across = 0.0 if count == 1 else (pin - (count - 1) * 0.5) * (2.0 * span / (count - 1))
            out.append((at, across, height))
    return tuple(out)


CANDIDATES: dict[str, StartPlan] = {
    "v1": StartPlan(name="v1"),
    # One row of studs moved from leg1 to the launch's own entry, where the
    # field is still a clump. No new geometry at all.
    "mix-launch": StartPlan(name="mix-launch", mixers=(("launch", 5, 0.07),)),
    "mix-both": StartPlan(
        name="mix-both", mixers=(("leg1", -1, 0.07), ("launch", 5, 0.07))
    ),
    # The stagger family. Every one of these scored worse than V1; kept so the
    # scan can be re-run against them rather than re-derived.
    "stagger-15": StartPlan(name="stagger-15", stagger=_stagger(0.15)),
    "stagger-30": StartPlan(name="stagger-30", stagger=_stagger(0.30)),
    "stagger-45": StartPlan(name="stagger-45", stagger=_stagger(0.45)),
    "stagger-60": StartPlan(name="stagger-60", stagger=_stagger(0.60)),
    # A merge tree in the fins: the four single-lane dividers stop where a lane
    # first narrows below a marble, the two that bound a merged pair run on,
    # and the centre one runs longest.
    "tree": StartPlan(name="tree", fins=(0.30, 0.70, 0.30, 0.92, 0.30, 0.70, 0.30)),
    "fins-long": StartPlan(name="fins-long", fins=(0.65,) * 7),
    "fins-short": StartPlan(name="fins-short", fins=(0.30,) * 7),
    # --- deflectors in the fan's second half, on top of mix-launch ---------
    #
    # Three staggered rows between FIN_END and the seam, which is the stretch
    # the measurement blames. The heights bracket what a marble at 8 to 11 wu/s
    # can be turned by without being levered over a 1.40 wall.
    "defl-3x10": StartPlan(
        name="defl-3x10",
        mixers=(("launch", 5, 0.07),),
        deflectors=_rows((0.58, 0.70, 0.82), (4, 3, 4), 0.10),
    ),
    "defl-3x16": StartPlan(
        name="defl-3x16",
        mixers=(("launch", 5, 0.07),),
        deflectors=_rows((0.58, 0.70, 0.82), (4, 3, 4), 0.16),
    ),
    "defl-3x22": StartPlan(
        name="defl-3x22",
        mixers=(("launch", 5, 0.07),),
        deflectors=_rows((0.58, 0.70, 0.82), (4, 3, 4), 0.22),
    ),
    # Five rows over a longer stretch, starting earlier - a longer shared
    # mixing tray rather than a denser one.
    "defl-5x16": StartPlan(
        name="defl-5x16",
        mixers=(("launch", 5, 0.07),),
        deflectors=_rows((0.52, 0.62, 0.72, 0.82, 0.92), (4, 3, 4, 3, 4), 0.16),
    ),
    # Studs on the launch's own first samples instead of in the trough, where
    # the field is one channel-width long and still only at 13 wu/s.
    "mix-launch-3row": StartPlan(
        name="mix-launch-3row",
        mixers=(("launch", 4, 0.10), ("launch", 10, 0.10), ("launch", 16, 0.10)),
    ),
    "mix-launch-tall": StartPlan(
        name="mix-launch-tall", mixers=(("launch", 5, 0.14), ("launch", 12, 0.14))
    ),
    # --- a paddle wheel at the launch entry --------------------------------
    #
    # Every static thing tried above makes the ordering *stronger*, and they all
    # fail the same way: a restriction in a converging funnel is a queue, and a
    # queue leaves in arrival order. A turning wheel is the one mechanism whose
    # output order is not monotone in its input order - a marble's wait is its
    # arrival time modulo the blade period - so it is the only candidate here
    # that can undo a stagger rather than sharpen it.
    #
    # Placed at the launch entry because that is the last place the field is
    # still a clump: 3.2 simulation units from first to last against a channel
    # 3.3 wide, where by leg1 it is eighteen. Four blades at `rate` rad/s pass
    # every 1.571/rate seconds, against the 0.32 s spread to be undone: 3.6
    # gives 0.44 s, 6.0 gives 0.26, 9.0 gives 0.17.
    "wheel-3.6": StartPlan(
        name="wheel-3.6", mixers=(("launch", 5, 0.07),), wheels=(("launch", 12, 3.6),)
    ),
    "wheel-6.0": StartPlan(
        name="wheel-6.0", mixers=(("launch", 5, 0.07),), wheels=(("launch", 12, 6.0),)
    ),
    "wheel-9.0": StartPlan(
        name="wheel-9.0", mixers=(("launch", 5, 0.07),), wheels=(("launch", 12, 9.0),)
    ),
    "wheel-6.0-early": StartPlan(
        name="wheel-6.0-early", mixers=(("launch", 5, 0.07),), wheels=(("launch", 7, 6.0),)
    ),
    "wheel-2x6": StartPlan(
        name="wheel-2x6",
        mixers=(("launch", 5, 0.07),),
        wheels=(("launch", 10, 6.0), ("launch", 20, -6.0)),
    ),
    # --- around the best of the first wheel scan --------------------------
    #
    # `wheel-6.0-early` - one wheel at launch sample 7 - was the first
    # candidate of any kind to *reduce* the span: 2.33 against V1's 3.71, with
    # losses at 0.56% against 16.31%. Earlier is better because the field is
    # tighter and slower there, so this scans the sample and the rate around it.
    "wheel-e4-6.0": StartPlan(
        name="wheel-e4-6.0", mixers=(("launch", 12, 0.07),), wheels=(("launch", 4, 6.0),)
    ),
    "wheel-e7-4.5": StartPlan(
        name="wheel-e7-4.5", mixers=(("launch", 14, 0.07),), wheels=(("launch", 7, 4.5),)
    ),
    "wheel-e7-7.5": StartPlan(
        name="wheel-e7-7.5", mixers=(("launch", 14, 0.07),), wheels=(("launch", 7, 7.5),)
    ),
    "wheel-e7-6.0-rev": StartPlan(
        name="wheel-e7-6.0-rev", mixers=(("launch", 14, 0.07),), wheels=(("launch", 7, -6.0),)
    ),
    "wheel-e5e14": StartPlan(
        name="wheel-e5e14",
        mixers=(("launch", 22, 0.07),),
        wheels=(("launch", 5, 6.0), ("launch", 14, -6.0)),
    ),
    "wheel-e7-only": StartPlan(name="wheel-e7-only", mixers=(), wheels=(("launch", 7, 6.0),)),
}


def _one(job):
    """One trial. The built machine is cached, but only the current one.

    Jobs are handed out candidate-major, so a worker builds each machine once
    per visit rather than once per trial, and holding a single machine bounds a
    worker's collider memory to one course instead of nine.
    """
    name, seed = job
    global _CACHE
    try:
        cache = _CACHE
    except NameError:
        cache = _CACHE = {}
    if cache.get("name") != name:
        from sloped.startlab import start_machine

        cache.clear()
        cache["name"] = name
        cache["machine"] = start_machine(plan=CANDIDATES[name])
    return name, run_trial(seed, machine=cache["machine"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=120)
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--only", nargs="*", default=None, help="candidate names to run")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    names = args.only or list(CANDIDATES)
    unknown = [n for n in names if n not in CANDIDATES]
    if unknown:
        parser.error(f"unknown candidates {unknown}; have {list(CANDIDATES)}")

    jobs = [(name, seed) for name in names for seed in range(args.first, args.first + args.seeds)]
    started = time.perf_counter()
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            done = list(pool.map(_one, jobs, chunksize=4))
    else:
        done = [_one(job) for job in jobs]
    wall = time.perf_counter() - started

    by_name: dict[str, list] = {name: [] for name in names}
    for name, result in done:
        by_name[name].append(result)

    marks = [n for n, _ in LAB_CHECKPOINTS]
    report = {}
    print(f"{len(jobs)} trials over {len(names)} candidates in {wall:.1f}s")
    header = (
        f"{'candidate':>12} | " + " | ".join(f"{m + ' span':>13}" for m in marks) + " | lost% | best/worst"
    )
    print(header)
    print("-" * len(header))
    for name in names:
        block = summarise(by_name[name])
        block["plan"] = CANDIDATES[name].describe()
        report[name] = block
        # A candidate can fail to reach a checkpoint at all - `defl-3x22`
        # jammed the fan and produced no ranks - so a missing span is printed
        # rather than formatted.
        spans = " | ".join(
            f"{block['rank_span'][m]['span']:13.3f}"
            if block["rank_span"][m]["span"] is not None
            else f"{'none':>13}"
            for m in marks
        )
        first = block["rank_span"][marks[0]]
        print(
            f"{name:>12} | {spans} | {block['lost_pct']:5.2f} | "
            f"{first['best_slot']}/{first['worst_slot']}"
        )
    print("-" * len(header))
    print("means by slot at the earliest checkpoint:")
    for name in names:
        means = report[name]["rank_span"][marks[0]]["means"]
        print(
            f"{name:>12} | "
            + " ".join("    -" if m is None else f"{m:5.2f}" for m in means)
        )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"seeds": args.seeds, "wall_seconds": round(wall, 2), "candidates": report}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

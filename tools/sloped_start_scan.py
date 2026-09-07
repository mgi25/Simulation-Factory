"""Score several candidate start geometries against each other, cheaply.

    python tools/sloped_start_scan.py --seeds 120
    python tools/sloped_start_scan.py --seeds 300 --only v1 stagger-30

Section 6 of the brief asks for exactly this loop: candidate geometry, 200-500
start-only trials, rank/slot statistics, compare, keep or reject, and no video
for any of it. The candidate list is in `CANDIDATES` below and each entry is a
`sloped.startlab.StartPlan` - physical geometry only, so a candidate cannot
score well by cheating.

Two numbers to read. `span` is the gap in mean rank between the strongest and
the weakest of the eight bays at the earliest checkpoint, in places: V1 is
3.615 and a fair start is 0. `trail%` is the share of marbles that had not got
85% of the way down the lab when the field settled, and it is there because the
first version of this scan did not have it - a paddle wheel that scored 0.55%
lost went on to jam 17% of the full course's field at the launch entry, and the
lab could not see it because a marble grinding along behind an obstruction has
neither left the channel nor stopped dead.
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


def _bumpers(marks, counts, height, radius, span=0.62, stagger=False):
    """Staggered bumper rows across a tray: `counts[i]` posts at `marks[i]`.

    Alternating counts put one row's posts in the previous row's gaps, so a
    marble that threads one meets the next off-centre. `span` is a fraction of
    the local half width and keeps the outermost post off the wall, because a
    post *at* the wall is a wall and narrows the tray instead of stirring it.
    """
    out = []
    for row, (at, count) in enumerate(zip(marks, counts)):
        shift = span * 0.5 if (stagger and row % 2) else 0.0
        for post in range(count):
            across = 0.0 if count == 1 else (post - (count - 1) * 0.5) * (2.0 * span / (count - 1))
            out.append((at, across + shift, height, radius))
    return tuple(out)


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
            out.append((at, across, height, 0.075))
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
    # --- after the real course said the early wheel jams ---------------------
    #
    # `wheel-6.0-early` scored best of everything here and then put 18.8% of the
    # full course's field into the stuck column, all of it at launch[0]. The lab
    # could not see it, because a marble grinding along behind an obstruction
    # has neither left the channel nor stopped dead; `THROUGH_MARK` and
    # `trailing` exist because of that, and this row is what they were added to
    # separate. On the real course, 12 seeds of eight:
    #
    #     wheel            finish  escape   stuck
    #     none              0.906   0.010   0.083
    #     sample  7, 6.0    0.802   0.010   0.188
    #     sample  7, 12.0   0.177   0.021   0.802
    #     sample 16, 6.0    0.885   0.010   0.104
    #     sample 24, 9.0    0.927   0.021   0.052
    #
    # A *faster* blade at sample 7 is worse, not better: it bats a 13 wu/s
    # marble back up the channel instead of flicking it through. Downstream is
    # where a wheel can be a wheel, because the field is at 30 wu/s there and
    # the blade tip is not.
    "no-wheel": StartPlan(name="no-wheel", mixers=(("launch", 5, 0.07),)),
    "wheel-s16-r6": StartPlan(
        name="wheel-s16-r6", mixers=(("launch", 5, 0.07),), wheels=(("launch", 16, 6.0),)
    ),
    "wheel-s24-r9": StartPlan(
        name="wheel-s24-r9", mixers=(("launch", 5, 0.07),), wheels=(("launch", 24, 9.0),)
    ),
    "wheel-s24-r6": StartPlan(
        name="wheel-s24-r6", mixers=(("launch", 5, 0.07),), wheels=(("launch", 24, 6.0),)
    ),
    "wheel-s32-r9": StartPlan(
        name="wheel-s32-r9", mixers=(("launch", 5, 0.07),), wheels=(("launch", 32, 9.0),)
    ),
    # --- V1.2: a different topology, not another variation of the funnel -----
    #
    # Everything above lives inside one continuous 7.34-unit taper from 5.46
    # wide to 1.88, and inside that topology the ordering is not removable: the
    # queue at the throat is ordered by lateral distance to it, which is bay
    # index. `tray` replaces the taper with converge-hold-converge, and the
    # bumpers only mean anything in the held stretch, where a deflected marble
    # has somewhere to go.
    #
    # The point is not that the funnel stops ordering the field. It is that
    # what the funnel orders is no longer a function of the bay.
    #
    # Bumpers have to be sparse. The first set - three posts a row at 0.62 of
    # the half width, 0.30 tall and 0.22 across - left gaps of one marble
    # diameter at the wall and stood taller than a marble's own centre, so they
    # were a barrier and not a bumper: two thirds of the field trailed. A post
    # is a bumper when a marble can pass either side without queueing, which
    # needs the gaps near two diameters and the height near the equator.
    "tray-plain": StartPlan(
        name="tray-plain",
    mixers=(("launch", 5, 0.07),),
        wheels=(("launch", 32, 9.0),),
        tray=(0.16, 0.56, 2.10),
        fall_profile=(0.42, 0.56),
    ),
    "tray-2x2": StartPlan(
        name="tray-2x2",
    mixers=(("launch", 5, 0.07),),
        wheels=(("launch", 32, 9.0),),
        tray=(0.16, 0.56, 2.10),
        fall_profile=(0.42, 0.56),
        deflectors=_bumpers((0.26, 0.44), (2, 2), 0.26, 0.24, span=0.50, stagger=True),
    ),
    "tray-212": StartPlan(
        name="tray-212",
    mixers=(("launch", 5, 0.07),),
        wheels=(("launch", 32, 9.0),),
        tray=(0.16, 0.56, 2.10),
        fall_profile=(0.42, 0.56),
        deflectors=_bumpers((0.24, 0.36, 0.48), (2, 1, 2), 0.26, 0.24, span=0.52),
    ),
    "tray-212-low": StartPlan(
        name="tray-212-low",
    mixers=(("launch", 5, 0.07),),
        wheels=(("launch", 32, 9.0),),
        tray=(0.16, 0.56, 2.10),
        fall_profile=(0.42, 0.56),
        deflectors=_bumpers((0.24, 0.36, 0.48), (2, 1, 2), 0.18, 0.24, span=0.52),
    ),
    "tray-212-fat": StartPlan(
        name="tray-212-fat",
    mixers=(("launch", 5, 0.07),),
        wheels=(("launch", 32, 9.0),),
        tray=(0.16, 0.56, 2.10),
        fall_profile=(0.42, 0.56),
        deflectors=_bumpers((0.24, 0.36, 0.48), (2, 1, 2), 0.26, 0.34, span=0.52),
    ),
    # A wider, longer tray - five marbles abreast rather than four.
    "tray-wide": StartPlan(
        name="tray-wide",
        mixers=(("launch", 5, 0.07),),
        wheels=(("launch", 32, 9.0),),
        tray=(0.15, 0.62, 2.45),
        fall_profile=(0.40, 0.55),
        deflectors=_bumpers((0.24, 0.38, 0.52), (2, 1, 2), 0.26, 0.26, span=0.52),
    ),
    # --- V1.2b: the mixing stretch moves onto the launch ---------------------
    #
    # The tray in the fan fails, and the reason is energy rather than shape.
    # The fan has 0.63 layout units of drop over 7.34, so once the run in and
    # the run out are paid for a held stretch inside it sits at 1.7 degrees. A
    # marble that loses speed on a bumper there never gets it back: every
    # bumper set trailed 60 to 75% of the field. And a *plain* wide tray is
    # worse than no tray, because it makes the final convergence sharper
    # without scrambling anything - slot means came out a clean symmetric V,
    # 7.38 5.67 4.01 1.85 1.34 3.25 5.19 7.32, which is the bias in its purest
    # form.
    #
    # The launch runs at 25 to 43 degrees. So the fan holds its width to the
    # seam and hands over to a launch that has been opened out, and the wide
    # mixing stretch and the convergence both happen there, where a deflected
    # marble is falling hard enough to carry on.
    "lw-plain": StartPlan(
        name="lw-plain",
        mixers=(("launch", 70, 0.07),),
        wheels=(("launch", 84, 9.0),),
        launch_width=(2.20, 26, 62),
        tray=(0.16, 1.0, 2.36),
        fall_profile=(0.42, 1.0),
    ),
    "lw-mix": StartPlan(
        name="lw-mix",
        mixers=(("launch", 14, 0.16, 0.16, 0.80), ("launch", 70, 0.07)),
        wheels=(("launch", 84, 9.0),),
        launch_width=(2.20, 26, 62),
        tray=(0.16, 1.0, 2.36),
        fall_profile=(0.42, 1.0),
    ),
    "lw-mix2": StartPlan(
        name="lw-mix2",
        mixers=(
            ("launch", 12, 0.16, 0.16, 0.80),
            ("launch", 24, 0.16, 0.16, 0.80),
            ("launch", 70, 0.07),
        ),
        wheels=(("launch", 84, 9.0),),
        launch_width=(2.20, 26, 62),
        tray=(0.16, 1.0, 2.36),
        fall_profile=(0.42, 1.0),
    ),
    "lw-mix2-tall": StartPlan(
        name="lw-mix2-tall",
        mixers=(
            ("launch", 12, 0.26, 0.22, 0.80),
            ("launch", 24, 0.26, 0.22, 0.80),
            ("launch", 70, 0.07),
        ),
        wheels=(("launch", 84, 9.0),),
        launch_width=(2.20, 26, 62),
        tray=(0.16, 1.0, 2.36),
        fall_profile=(0.42, 1.0),
    ),
    # Wider still, and converging later.
    "lw-wide-mix2": StartPlan(
        name="lw-wide-mix2",
        mixers=(
            ("launch", 12, 0.22, 0.20, 0.82),
            ("launch", 26, 0.22, 0.20, 0.82),
            ("launch", 78, 0.07),
        ),
        wheels=(("launch", 92, 9.0),),
        launch_width=(2.70, 32, 72),
        tray=(0.16, 1.0, 2.71),
        fall_profile=(0.42, 1.0),
    ),
    # A gentler opening, converging over most of the launch rather than a
    # third of it. `lw-plain` at 2.2x lost 34% of the field - not in the wide
    # stretch, which is fine, but at launch[70..100], *after* the convergence:
    # a wide fast field squeezed back to 1.88 over 36 samples is thrown
    # sideways and leaves where the launch banks into its first turn. The
    # convergence has to happen somewhere, and it either orders the field
    # slowly or ejects it quickly.
    "lw-soft-plain": StartPlan(
        name="lw-soft-plain",
        mixers=(("launch", 104, 0.07),),
        wheels=(("launch", 112, 9.0),),
        launch_width=(1.55, 30, 96),
        tray=(0.16, 1.0, 1.66),
        fall_profile=(0.42, 1.0),
    ),
    "lw-soft": StartPlan(
        name="lw-soft",
        mixers=(
            ("launch", 14, 0.16, 0.16, 0.80),
            ("launch", 30, 0.16, 0.16, 0.80),
            ("launch", 104, 0.07),
        ),
        wheels=(("launch", 112, 9.0),),
        launch_width=(1.55, 30, 96),
        tray=(0.16, 1.0, 1.66),
        fall_profile=(0.42, 1.0),
    ),
    "lw-mid": StartPlan(
        name="lw-mid",
        mixers=(
            ("launch", 14, 0.18, 0.18, 0.80),
            ("launch", 32, 0.18, 0.18, 0.80),
            ("launch", 104, 0.07),
        ),
        wheels=(("launch", 112, 9.0),),
        launch_width=(1.85, 34, 100),
        tray=(0.16, 1.0, 1.98),
        fall_profile=(0.42, 1.0),
    ),
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
        f"{'candidate':>16} | "
        + " | ".join(f"{m + ' span':>13}" for m in marks)
        + " | lost% | trail% | best/worst"
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
            f"{name:>16} | {spans} | {block['lost_pct']:5.2f} | "
            f"{block['trailing_pct']:6.2f} | "
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

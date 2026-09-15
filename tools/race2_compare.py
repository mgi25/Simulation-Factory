"""Race #2 against Race #1, on one instrument.

    python tools/race2_compare.py --seeds=40

The brief's Part U says not to ask which is prettier but which changes leader
more often, has shorter dead periods, keeps racers larger and reveals action
better. Three of those four are measurable here; racer size is measured by
`race2.framing` on the solved camera tracks and is quoted in the documentation.

## The instrument problem, and how it is solved

`sloped.race` counts a lead change whenever the progress ordering's first entry
differs from the last sample's. `race2.race` counts one only when a challenger
is ahead by `LEAD_MARGIN` - 0.8 layout units - because without that, eight
marbles level across a pan trade places on every 60 Hz sample and the count
measures the sample rate. Race #1's raw number is inflated by exactly that
effect, so quoting the two side by side would flatter Race #2 for a reason that
has nothing to do with its geometry.

So this tool re-derives **both** counts under the sticky rule. `StickySloped`
subclasses Race #1's own race and replaces only its ordering; nothing else
about Race #1 changes, and the numbers it produces for Race #2 are the package's
own. Race #1's raw count is printed beside the sticky one so the size of the
correction is visible rather than hidden.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from race2.race import LEAD_MARGIN


def _sticky(previous, results, progress_of, margin):
    """The ordering with hysteresis - `Race2._sticky_order`, made reusable."""
    finished = sorted(
        (r for r in results if getattr(r, "finish_order", None)),
        key=lambda r: r.finish_order,
    )
    running = [r for r in results if not getattr(r, "finish_order", None)]
    if not previous:
        running.sort(key=lambda r: -progress_of(r))
        return [r.marble_id for r in finished] + [r.marble_id for r in running]
    place = {marble: index for index, marble in enumerate(previous)}
    running.sort(key=lambda r: place.get(r.marble_id, 99))
    ids = [r.marble_id for r in running]
    table = {r.marble_id: progress_of(r) for r in running}
    changed = True
    while changed:
        changed = False
        for index in range(len(ids) - 1):
            ahead, behind = ids[index], ids[index + 1]
            if table[behind] - table[ahead] >= margin:
                ids[index], ids[index + 1] = behind, ahead
                changed = True
    return [r.marble_id for r in finished] + ids


def race_one(seed: int, duration: float) -> dict:
    """One sloped race, with the ordering re-counted under the sticky rule."""
    from marble3d.config import DEFAULT_CONFIG
    from sloped.course import sloped_course
    from sloped.race import SlopedRace

    machine = sloped_course(routes="both")
    race = SlopedRace(machine, DEFAULT_CONFIG, seed, 8)
    limit = int(round(duration * DEFAULT_CONFIG.physics.physics_hz))
    started = time.perf_counter()
    order: list[int] = []
    leader = None
    sticky_changes = 0
    marks: list[float] = []
    try:
        while race.ticks < limit and not race.finished:
            race.step()
            if race.ticks % race.LOCATE_EVERY:
                continue
            order = _sticky(order, list(race.results.values()),
                            lambda r: r.progress, LEAD_MARGIN)
            if order and order[0] != leader:
                if leader is not None:
                    sticky_changes += 1
                    marks.append(race.elapsed)
                leader = order[0]
        wall = time.perf_counter() - started
        finished = sum(1 for r in race.results.values() if r.finish_order)
        times = sorted(r.finish_time for r in race.results.values() if r.finish_time)
    finally:
        race.close()
    return {
        "seed": seed,
        "finished": finished,
        "racers": len(race.results),
        "raw_lead_changes": race.lead_changes,
        "lead_changes": sticky_changes,
        "lead_marks": marks,
        "first_finish": times[0] if times else None,
        "last_finish": times[-1] if times else None,
        "podium_gap": (times[1] - times[0]) if len(times) > 1 else None,
        "wall": wall,
    }


def race_two(seed: int, duration: float) -> dict:
    from race2 import courses
    from race2.events import extract
    from race2.race import run_race

    course = courses.build("switchyard")
    outcome, _ = run_race(course, seed=seed, duration=duration)
    timeline = extract(outcome, course, outcome.sim_events)
    times = sorted(r.finish_time for r in outcome.racers if r.finish_time)
    _at, gap = timeline.longest_gap()
    return {
        "seed": seed,
        "finished": outcome.finished,
        "racers": len(outcome.racers),
        "lead_changes": outcome.lead_changes,
        "lead_marks": [when for when, _who in outcome.leader_series][1:],
        "first_finish": times[0] if times else None,
        "last_finish": times[-1] if times else None,
        "podium_gap": outcome.podium_gap(),
        "events": len(timeline.events),
        "density": timeline.density(),
        "longest_gap": gap,
        "wall": outcome.wall_seconds,
    }


def _leader_gap(row: dict) -> float:
    """The longest span with no change of leader, in seconds.

    The one content number both courses produce natively and that means the
    same thing in each. Measured from the first finish backwards as well as
    forwards, so a course that settles early is penalised for settling.
    """
    marks = list(row.get("lead_marks") or [])
    end = row.get("last_finish") or 0.0
    bounds = [0.0] + marks + [end]
    return max((b - a for a, b in zip(bounds, bounds[1:])), default=end)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=40)
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--out", default="docs/validation/race2/compare_race1.json")
    args = parser.parse_args()

    seeds = list(range(1, args.seeds + 1))
    rows = {"race1": [], "race2": []}
    for index, seed in enumerate(seeds, start=1):
        rows["race1"].append(race_one(seed, args.duration))
        rows["race2"].append(race_two(seed, args.duration))
        if index % 5 == 0 or index == len(seeds):
            print(f"  {index}/{len(seeds)}", flush=True)

    def mean(which: str, key: str) -> float:
        values = [r[key] for r in rows[which] if r.get(key) is not None]
        return statistics.fmean(values) if values else 0.0

    print()
    print(f"{'':<26}{'Race #1 sloped':>16}{'Race #2 switchyard':>20}")
    print("-" * 62)
    lines = [
        ("racers finishing", "%.1f%%", lambda w: 100.0 * sum(r["finished"] for r in rows[w])
         / max(sum(r["racers"] for r in rows[w]), 1)),
        ("races with all eight", "%.0f%%", lambda w: 100.0 * sum(
            1 for r in rows[w] if r["finished"] == r["racers"]) / max(len(rows[w]), 1)),
        ("lead changes (sticky)", "%.2f", lambda w: mean(w, "lead_changes")),
        ("longest no-lead-change", "%.2f s", lambda w: statistics.fmean(
            [_leader_gap(r) for r in rows[w]])),
        ("first finish", "%.2f s", lambda w: mean(w, "first_finish")),
        ("last finish", "%.2f s", lambda w: mean(w, "last_finish")),
        ("podium gap", "%.3f s", lambda w: mean(w, "podium_gap")),
        ("wall seconds per race", "%.1f s", lambda w: mean(w, "wall")),
    ]
    summary = {}
    for label, fmt, func in lines:
        a, b = func("race1"), func("race2")
        summary[label] = {"race1": round(a, 4), "race2": round(b, 4)}
        print(f"{label:<26}{fmt % a:>16}{fmt % b:>20}")
    raw = mean("race1", "raw_lead_changes")
    print(f"{'(Race #1 raw count)':<26}{'%.2f' % raw:>16}{'-':>20}")
    summary["race1_raw_lead_changes"] = round(raw, 4)
    summary["race2_events_per_second"] = round(mean("race2", "density"), 4)
    summary["race2_longest_event_gap"] = round(mean("race2", "longest_gap"), 4)
    print(f"\nRace #2 only: {summary['race2_events_per_second']:.2f} events/s, "
          f"longest event gap {summary['race2_longest_event_gap']:.2f} s")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"seeds": len(seeds), "summary": summary, "rows": rows}, handle, indent=1)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

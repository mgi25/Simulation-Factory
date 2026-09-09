"""Run many seeds of the sloped race and report what the course does.

Sections 15, 16, 22, 23, 27, 29 and 45 of the brief, in one pass, because they
all want the same thousand races and only differ in what they read out of them.

    python tools/sloped_benchmark.py --seeds 1000 --out docs/validation/sloped_race_v1/fairness.json

## Start-slot bias, and why the answer is about slots and not marbles

`marble3d.seeds` permutes marble *identity* across the physical start bays, so
marble 3 begins in bay 0 in one seed and bay 7 in the next while every marble's
mass, radius, restitution and friction stay identical. A slot's win rate is
therefore a property of the bay - of the geometry - and not of a racer, which
is what section 15 asks for and what makes the number worth measuring at all:
eight identical spheres in eight bays, and if bay 4 wins twice as often as bay
0 that is the course talking.

Reported per slot: mean rank at each checkpoint, win rate, podium rate, finish
rate, failure rate, and the rank variance. Reported over slots: the
strongest-to-weakest win ratio, which section 16 wants at or under about 2.0 to
2.5, and the Spearman correlation between slot and finish rank at each
checkpoint - which is the number that says whether the early mixing did
anything, because a course that shuffles has a correlation near zero at halfway
whatever it had at the first descent.

## Route balance

Entry counts, finish rate, mean and median time, mean rank change from the fork
to the finish, and the failure rate, per route. Section 23 asks that neither
route dominate *outcome*; usage can be uneven and that is a finding, not a
fault, so both are reported separately.

## Parallelism

One process per core, each running its own PyBullet client on its own seeds.
The physics is per-process deterministic and no state crosses between them, so
the result does not depend on how the work was split - `--workers 1` and
`--workers 12` produce the same JSON. That is checked by
`tests/test_sloped_benchmark.py` on a small sweep rather than asserted.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Iterable, Sequence

sys.path.insert(0, os.getcwd())

from marble3d.config import DEFAULT_CONFIG, CoreConfig
from sloped import joins
from sloped.course import facts as course_facts, sloped_course
from sloped.race import CHECKPOINTS, run_race


def warm_mesh_cache() -> int:
    """Write every collider OBJ once, in the parent, before any worker starts.

    `marble3d.mesh.cached_obj` writes a content-named file through a `.partial`
    and `os.replace`, which is atomic on POSIX and *fails* on Windows when the
    destination is open in another process. Eight workers building the same
    course at the same moment therefore collide on the same fifteen files, and
    the whole sweep dies on a PermissionError several minutes in - which is how
    the first 32-seed run ended.

    Building the course once here fills the cache, so every worker finds the
    files present and takes the `os.path.exists` branch. Returns the count, so
    the report can say the cache was warm rather than assuming it.
    """
    from marble3d.world import MarbleWorld

    world = MarbleWorld(DEFAULT_CONFIG)
    try:
        machine = sloped_course(routes="both")
        machine.build(world)
        return len(world.colliders)
    finally:
        world.close()


def run_batch(args: tuple[Sequence[int], int, float]) -> list[dict[str, Any]]:
    """One worker: build the course once, then run its seeds through it.

    The machine is rebuilt per race because `MarbleSimulation` takes ownership
    of a world and the module geometry is cached on the module objects, so
    sharing one machine across races would share its mesh cache and nothing
    else - which is exactly what is wanted, and is why the course is built here
    rather than passed in.
    """
    seeds, marble_count, duration, routes = args
    out: list[dict[str, Any]] = []
    for seed in seeds:
        outcome, _ = run_race(
            seed=seed,
            machine=sloped_course(routes=routes),
            marble_count=marble_count,
            duration=duration,
        )
        out.append(outcome.to_json())
    return out


def _spearman(pairs: Sequence[tuple[float, float]]) -> float | None:
    """Rank correlation, with ties averaged. None if there is nothing to rank."""
    if len(pairs) < 3:
        return None

    def ranked(values: Sequence[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda index: values[index])
        ranks = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
                stop += 1
            mean = 0.5 * (index + stop) + 1.0
            for position in range(index, stop + 1):
                ranks[order[position]] = mean
            index = stop + 1
        return ranks

    xs = ranked([p[0] for p in pairs])
    ys = ranked([p[1] for p in pairs])
    n = len(pairs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    top = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    left = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    right = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    return None if left * right == 0.0 else top / (left * right)


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson's r, or None when one side does not vary.

    Used on eight slot means rather than on every racer, because a single
    race's finish order is a permutation and correlates with nothing; the
    question is whether a bay is *consistently* ahead.
    """
    if len(xs) < 3:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx * syy < 1e-15:
        return None
    return round(sxy / (sxx * syy) ** 0.5, 4)


def summarise(races: Sequence[dict[str, Any]], slots: int = 8) -> dict[str, Any]:
    """Everything the brief asks to be read out of a sweep."""
    by_slot: dict[int, dict[str, Any]] = {
        slot: {
            "starts": 0,
            "finishes": 0,
            "wins": 0,
            "podiums": 0,
            "escaped": 0,
            "stuck": 0,
            "ranks": defaultdict(list),
            "finish_ranks": [],
            "routes": Counter(),
        }
        for slot in range(slots)
    }
    by_route: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "entries": 0,
            "finishes": 0,
            "wins": 0,
            "times": [],
            "escaped": 0,
            "stuck": 0,
            "rank_change": [],
            "finish_ranks": [],
        }
    )

    finished_races = 0
    durations: list[float] = []
    wall: list[float] = []
    lead_changes: list[int] = []
    overtakes: list[int] = []
    lock_fractions: list[float] = []
    margins: list[float] = []
    winner_worst: list[int] = []
    top_speeds: list[float] = []
    travel: list[float] = []
    falling: list[float] = []
    penetration: list[float] = []
    actuator: list[float] = []
    pairs: list[float] = []
    collisions: list[int] = []
    lost_sites: Counter = Counter()
    slot_rank_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    finishers_per_race: Counter = Counter()

    for race in races:
        durations.append(race["seconds"])
        wall.append(race["wall_seconds"])
        lead_changes.append(race["lead_changes"])
        overtakes.append(race["overtakes"])
        top_speeds.append(race["top_speed"])
        travel.append(race["max_travel_per_tick"])
        falling.append(race["max_travel_falling"])
        penetration.append(race["worst_penetration"])
        actuator.append(race["worst_actuator_overlap"])
        pairs.append(race["worst_marble_overlap"])
        collisions.append(race["collisions"])
        finishers_per_race[race["finished"]] += 1
        if race["finished"] == len(race["racers"]):
            finished_races += 1
        if race["winner_lock_fraction"] is not None:
            lock_fractions.append(race["winner_lock_fraction"])
        if race["final_margin"] is not None:
            margins.append(race["final_margin"])
        if race["winner_worst_rank"] is not None:
            winner_worst.append(race["winner_worst_rank"])

        for racer in race["racers"]:
            slot = racer["slot"]
            entry = by_slot[slot]
            entry["starts"] += 1
            route = racer["route"]
            entry["routes"][route or "unrouted"] += 1
            for name, rank in racer["ranks"].items():
                entry["ranks"][name].append(rank)
            if racer["state"] == "finished":
                entry["finishes"] += 1
                entry["finish_ranks"].append(racer["order"])
                if racer["order"] == 1:
                    entry["wins"] += 1
                if racer["order"] <= 3:
                    entry["podiums"] += 1
                for name, rank in racer["ranks"].items():
                    slot_rank_pairs[name].append((slot, racer["order"]))
                slot_rank_pairs["finish"].append((slot, racer["order"]))
            elif racer["state"] == "escaped":
                entry["escaped"] += 1
            else:
                entry["stuck"] += 1
            if racer["state"] != "finished" and racer["last_touch"]:
                lost_sites[f"{racer['last_touch'][0]}[{(racer['last_touch'][1] // 20) * 20}]"] += 1

            if route:
                lane = by_route[route]
                lane["entries"] += 1
                if racer["state"] == "finished":
                    lane["finishes"] += 1
                    lane["times"].append(racer["time"])
                    lane["finish_ranks"].append(racer["order"])
                    if racer["order"] == 1:
                        lane["wins"] += 1
                    early = racer["ranks"].get("half")
                    if early is not None:
                        lane["rank_change"].append(early - racer["order"])
                elif racer["state"] == "escaped":
                    lane["escaped"] += 1
                else:
                    lane["stuck"] += 1

    def mean(values: Iterable[float]) -> float | None:
        values = list(values)
        return None if not values else sum(values) / len(values)

    slots_out = {}
    for slot, entry in by_slot.items():
        starts = max(entry["starts"], 1)
        slots_out[str(slot)] = {
            "starts": entry["starts"],
            "finish_rate": round(entry["finishes"] / starts, 4),
            "win_rate": round(entry["wins"] / starts, 4),
            "podium_rate": round(entry["podiums"] / starts, 4),
            "escape_rate": round(entry["escaped"] / starts, 4),
            "stuck_rate": round(entry["stuck"] / starts, 4),
            "mean_rank": {
                name: round(mean(values), 3)
                for name, values in sorted(entry["ranks"].items())
                if values
            },
            "mean_finish_rank": None
            if not entry["finish_ranks"]
            else round(mean(entry["finish_ranks"]), 3),
            "finish_rank_variance": None
            if len(entry["finish_ranks"]) < 2
            else round(statistics.pvariance(entry["finish_ranks"]), 3),
            "routes": dict(entry["routes"]),
        }

    win_rates = {slot: data["win_rate"] for slot, data in slots_out.items()}
    positive = [v for v in win_rates.values() if v > 0.0]
    strongest = max(win_rates, key=lambda k: win_rates[k]) if win_rates else None
    weakest = min(win_rates, key=lambda k: win_rates[k]) if win_rates else None
    ratio = None
    if positive and min(win_rates.values()) > 0.0:
        ratio = max(win_rates.values()) / min(win_rates.values())

    # --- the fairness shapes section 6 asks for ---------------------------
    #
    # **A win ratio alone is the wrong single number and this course is why.**
    # It is undefined the moment any bay wins nothing - which happens at every
    # sample size this benchmark runs, because eight bays sharing a few hundred
    # wins leave one at zero often enough - and when it is defined it is a ratio
    # of two extremes out of eight and moves on one race. So the same three
    # statistics the start lab reports are computed here on the *full race*,
    # where the brief's own target lives:
    #
    #   sd            the standard deviation of the eight slot mean finish
    #                 ranks, which privileges no shape. The start lab's own
    #                 numbers moved from 0.863 to 0.376 on this measure while
    #                 the two correlations disagreed about which start was
    #                 fairer, each measuring its own shape.
    #   slot r        Pearson's r between the bay index and its mean finish
    #                 rank: a west-to-east tilt.
    #   centre r      the same against |bay - 3.5|: a centre-versus-edge
    #                 advantage, which is symmetric and which a slot r cannot
    #                 see at all.
    #
    # All three on **finish rank** rather than win rate, because a rank uses
    # every racer of every race and a win uses one of eight.
    ranked = [
        (int(slot), data["mean_finish_rank"])
        for slot, data in sorted(slots_out.items(), key=lambda kv: int(kv[0]))
        if data["mean_finish_rank"] is not None
    ]
    fairness: dict[str, Any] = {
        "slots_ranked": len(ranked),
        "win_rate_ratio": None if ratio is None else round(ratio, 4),
        "win_rate_spread_points": (
            None if not win_rates
            else round(100.0 * (max(win_rates.values()) - min(win_rates.values())), 2)
        ),
    }
    if len(ranked) >= 3:
        means = [value for _slot, value in ranked]
        average = sum(means) / len(means)
        fairness["slot_mean_rank_sd"] = round(
            (sum((m - average) ** 2 for m in means) / len(means)) ** 0.5, 4
        )
        fairness["slot_mean_rank_span"] = round(max(means) - min(means), 4)
        fairness["slot_rank_correlation"] = _pearson(
            [float(slot) for slot, _v in ranked], means
        )
        fairness["centre_rank_correlation"] = _pearson(
            [abs(slot - (len(slots_out) - 1) / 2.0) for slot, _v in ranked], means
        )
        fairness["best_slot"] = min(ranked, key=lambda row: row[1])[0]
        fairness["worst_slot"] = max(ranked, key=lambda row: row[1])[0]

    routes_out = {}
    for route, lane in by_route.items():
        entries = max(lane["entries"], 1)
        routes_out[route] = {
            "entries": lane["entries"],
            "entry_share": round(lane["entries"] / max(sum(l["entries"] for l in by_route.values()), 1), 4),
            "finish_rate": round(lane["finishes"] / entries, 4),
            "win_rate": round(lane["wins"] / entries, 4),
            "escape_rate": round(lane["escaped"] / entries, 4),
            "stuck_rate": round(lane["stuck"] / entries, 4),
            "mean_time": None if not lane["times"] else round(mean(lane["times"]), 4),
            "median_time": None if not lane["times"] else round(statistics.median(lane["times"]), 4),
            "mean_finish_rank": None
            if not lane["finish_ranks"]
            else round(mean(lane["finish_ranks"]), 3),
            "mean_rank_change_from_half": None
            if not lane["rank_change"]
            else round(mean(lane["rank_change"]), 3),
        }

    return {
        "races": len(races),
        "racers": sum(len(r["racers"]) for r in races),
        "reliability": {
            "all_finished_races": finished_races,
            "all_finished_rate": round(finished_races / max(len(races), 1), 4),
            "finishers_histogram": {str(k): v for k, v in sorted(finishers_per_race.items())},
            "finish_rate": round(
                sum(r["finished"] for r in races) / max(sum(len(r["racers"]) for r in races), 1), 4
            ),
            "escape_rate": round(
                sum(r["escaped"] for r in races) / max(sum(len(r["racers"]) for r in races), 1), 4
            ),
            "stuck_rate": round(
                sum(r["stuck"] for r in races) / max(sum(len(r["racers"]) for r in races), 1), 4
            ),
            "loss_sites": dict(lost_sites.most_common(12)),
            # Three penetration numbers and two travel numbers, because the
            # single worst case of each was being set by something the budget
            # is not about: `marble3d.simulation.RunStats` has the measurement.
            "worst_penetration": round(min(penetration), 5) if penetration else None,
            "worst_actuator_overlap": round(min(actuator), 5) if actuator else None,
            "worst_marble_overlap": round(min(pairs), 5) if pairs else None,
            "max_travel_per_tick": round(max(travel), 5) if travel else None,
            "max_travel_falling": round(max(falling), 5) if falling else None,
            "travel_budget": DEFAULT_CONFIG.marble.travel_budget
            * DEFAULT_CONFIG.marble.diameter,
        },
        "duration": {
            "mean": round(mean(durations), 4),
            "median": round(statistics.median(durations), 4),
            "min": round(min(durations), 4),
            "max": round(max(durations), 4),
        },
        "fairness": {
            "slots": slots_out,
            "strongest_slot": strongest,
            "weakest_slot": weakest,
            "strongest_win_rate": max(win_rates.values()) if win_rates else None,
            "weakest_win_rate": min(win_rates.values()) if win_rates else None,
            "win_rate_ratio": None if ratio is None else round(ratio, 3),
            "expected_win_rate": round(1.0 / max(slots, 1), 4),
            "slot_rank_spearman": {
                name: None if _spearman(pairs) is None else round(_spearman(pairs), 4)
                for name, pairs in sorted(slot_rank_pairs.items())
            },
            # The three shapes section 6 asks for, on finish rank. See
            # `_pearson` and the block that builds `fairness` above.
            **fairness,
        },
        "routes": routes_out,
        "quality": {
            "mean_lead_changes": round(mean(lead_changes), 3),
            "mean_overtakes": round(mean(overtakes), 3),
            "mean_winner_lock_fraction": None
            if not lock_fractions
            else round(mean(lock_fractions), 4),
            "median_winner_lock_fraction": None
            if not lock_fractions
            else round(statistics.median(lock_fractions), 4),
            "mean_final_margin": None if not margins else round(mean(margins), 4),
            "median_final_margin": None if not margins else round(statistics.median(margins), 4),
            "mean_winner_worst_rank": None if not winner_worst else round(mean(winner_worst), 3),
            "mean_collisions": round(mean(collisions), 2),
            "mean_top_speed": round(mean(top_speeds), 3),
        },
        "performance": {
            "mean_wall_seconds": round(mean(wall), 4),
            "mean_sim_seconds": round(mean(durations), 4),
            "sim_per_wall": round(sum(durations) / max(sum(wall), 1e-9), 3),
            "seeds_per_wall_second": round(len(races) / max(sum(wall), 1e-9), 4),
        },
    }


def pick_seed(races: Sequence[dict[str, Any]], slots: int = 8) -> dict[str, Any]:
    """Score the clean races on entertainment and return the ranked shortlist.

    Section 28 says not to optimise blindly to one score, and section 30 lists
    what a good race has. So the score is a sum of five terms, each normalised
    and each visible in the output, and the shortlist is reported with its
    components so the pick can be argued with rather than taken on trust.

    A race is only eligible if every marble finished, nothing escaped and
    nothing jammed: an exciting race with a marble missing is not a candidate.
    """
    scored: list[dict[str, Any]] = []
    for race in races:
        if race["finished"] != slots or race["escaped"] or race["stuck"]:
            continue
        lock = race["winner_lock_fraction"] or 0.0
        margin = race["final_margin"] or 0.0
        worst = race["winner_worst_rank"] or 1
        routes = Counter(r["route"] for r in race["racers"] if r["route"])
        split = min(routes.values()) / max(sum(routes.values()), 1) if len(routes) > 1 else 0.0
        terms = {
            # How long the winner was not in front, as a fraction of the race.
            "lock": round(min(lock / 0.6, 1.0), 4),
            # A close finish, saturating at two seconds.
            "margin": round(max(0.0, 1.0 - margin / 2.0), 4),
            # The winner having been down the order at some point.
            "comeback": round(min((worst - 1) / 5.0, 1.0), 4),
            # Both routes used, best at an even split.
            "split": round(split / 0.5, 4),
            # Positions actually changing hands.
            "turnover": round(min(race["lead_changes"] / 6.0, 1.0), 4),
        }
        scored.append(
            {
                "seed": race["seed"],
                "score": round(sum(terms.values()), 4),
                "terms": terms,
                "seconds": race["seconds"],
                "lead_changes": race["lead_changes"],
                "overtakes": race["overtakes"],
                "winner_lock_fraction": race["winner_lock_fraction"],
                "final_margin": race["final_margin"],
                "winner_worst_rank": race["winner_worst_rank"],
                "winner_slot": next(
                    (r["slot"] for r in race["racers"] if r["order"] == 1), None
                ),
                "winner_route": next(
                    (r["route"] for r in race["racers"] if r["order"] == 1), None
                ),
                "routes": dict(routes),
            }
        )
    scored.sort(key=lambda entry: -entry["score"])
    return {"eligible": len(scored), "shortlist": scored[:12]}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, default=500)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--chunk", type=int, default=8)
    parser.add_argument("--out", default="")
    parser.add_argument("--races-out", default="", help="every race's own JSON, for seed picking")
    parser.add_argument(
        "--routes",
        default="both",
        choices=("blue", "both"),
        help="which routes the course offers; \"both\" builds the fork",
    )
    args = parser.parse_args(argv)

    seeds = list(range(args.first_seed, args.first_seed + args.seeds))
    batches = [
        (seeds[index : index + args.chunk], args.marbles, args.duration, args.routes)
        for index in range(0, len(seeds), args.chunk)
    ]

    chunks = warm_mesh_cache()
    print(f"mesh cache warm: {chunks} collider chunks", file=sys.stderr, flush=True)

    started = time.perf_counter()
    races: list[dict[str, Any]] = []
    if args.workers <= 1:
        for batch in batches:
            races.extend(run_batch(batch))
            print(f"  {len(races)}/{len(seeds)}", file=sys.stderr, flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for done in pool.map(run_batch, batches):
                races.extend(done)
                print(f"  {len(races)}/{len(seeds)}", file=sys.stderr, flush=True)
    elapsed = time.perf_counter() - started
    races.sort(key=lambda race: race["seed"])

    report = summarise(races, slots=args.marbles)
    report["selection"] = pick_seed(races, slots=args.marbles)
    report["course"] = course_facts(sloped_course(routes=args.routes))
    report["routes_built"] = args.routes
    report["checkpoints"] = {name: fraction for name, fraction in CHECKPOINTS}
    report["fork_sample"] = joins.FORK_SAMPLE
    report["config"] = DEFAULT_CONFIG.to_json()
    report["performance"]["wall_seconds_total"] = round(elapsed, 3)
    report["performance"]["workers"] = args.workers
    report["performance"]["collider_chunks"] = chunks
    report["performance"]["seeds_per_second"] = round(len(seeds) / max(elapsed, 1e-9), 4)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, indent=1, sort_keys=True)
            handle.write("\n")
        print(f"wrote {args.out}")
    if args.races_out:
        os.makedirs(os.path.dirname(args.races_out) or ".", exist_ok=True)
        with open(args.races_out, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(races, handle, separators=(",", ":"))
            handle.write("\n")
        print(f"wrote {args.races_out}")

    reliability = report["reliability"]
    fairness = report["fairness"]
    print(
        f"{report['races']} races, {report['racers']} racers in {elapsed:.1f} s "
        f"({report['performance']['seeds_per_second']:.2f} seeds/s, "
        f"{report['performance']['sim_per_wall']:.2f} sim s / wall s)"
    )
    print(
        f"  finish {reliability['finish_rate']:.3f}  escape {reliability['escape_rate']:.3f}  "
        f"stuck {reliability['stuck_rate']:.3f}  all-eight races {reliability['all_finished_rate']:.3f}"
    )
    print(
        f"  slot win rates: "
        + " ".join(f"{s}:{d['win_rate']:.3f}" for s, d in sorted(fairness["slots"].items()))
    )
    print(
        f"  strongest {fairness['strongest_slot']} weakest {fairness['weakest_slot']} "
        f"ratio {fairness['win_rate_ratio']}  spearman(finish) "
        f"{fairness['slot_rank_spearman'].get('finish')}"
    )
    for route, data in sorted(report["routes"].items()):
        print(
            f"  route {route:9s} entries {data['entries']:5d} share {data['entry_share']:.3f} "
            f"finish {data['finish_rate']:.3f} win {data['win_rate']:.3f} "
            f"median {data['median_time']}"
        )
    print(f"  loss sites: {reliability['loss_sites']}")
    print(
        f"  validation: travel {reliability['max_travel_per_tick']} in the machine, "
        f"{reliability['max_travel_falling']} falling out of it; penetration "
        f"track {reliability['worst_penetration']}, actuator "
        f"{reliability['worst_actuator_overlap']}, marble-on-marble "
        f"{reliability['worst_marble_overlap']}"
    )
    print(f"  eligible seeds {report['selection']['eligible']}")
    for entry in report["selection"]["shortlist"][:5]:
        print(
            f"    seed {entry['seed']:6d} score {entry['score']:.3f} "
            f"lock {entry['winner_lock_fraction']} margin {entry['final_margin']} "
            f"leads {entry['lead_changes']} routes {entry['routes']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

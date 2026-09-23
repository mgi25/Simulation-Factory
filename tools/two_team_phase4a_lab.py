"""The Phase 4A laboratory: the population, the fairness proof and the shortlist.

Three jobs, deliberately in one tool because they share a configuration and a
seed convention:

``batch``
    Run a deterministic seed block and write the distributions the brief asks
    for - per-shell pass rate, race success, duration, population by team, lead
    changes, event density, colour win split and every solver instrument. The
    batch itself is `satisfying.multishell_cli.run_batch`, so the archive
    format and the re-summarising path are the ones the rest of the project
    already uses; nothing here re-implements a record.

``fairness``
    The label-swap test. For each sampled seed, simulate normally and again
    with ``team_swap=True``, then prove the *physics* is bit-identical and only
    the labels moved. Both digests come out of the simulation itself, so this
    compares what happened rather than what was intended.

``shortlist``
    Apply the named selection rule to a batch's records and write the ranked
    candidate list, with the variety buckets the human-review set is drawn
    from.

Nothing here decides anything about the video. It writes the numbers a person
reads before watching six clips.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from satisfying.multishell import (  # noqa: E402
    DEFAULT_CONFIG,
    MultishellConfig,
    difficulty_profile,
    simulate,
)
from satisfying.multishell_cli import _rehydrate, run_batch  # noqa: E402
from satisfying.multishell_evaluator import DEFAULT_THRESHOLDS, summarise  # noqa: E402

_CONFIG = DEFAULT_CONFIG


def _init(payload: dict[str, Any]) -> None:
    global _CONFIG
    _CONFIG = MultishellConfig.from_dict(payload)


# --------------------------------------------------------------------------
# Fairness
# --------------------------------------------------------------------------

#: Event fields that carry a label rather than a position, a velocity or a
#: time. They are removed before two runs' event streams are compared, because
#: they are precisely what a swap is *allowed* to change.
LABEL_FIELDS = (
    "team_id",
    "other_team_id",
    "team_name",
    "team_cumulative",
    "team_contributors",
    "largest_team",
    "population_by_team",
    "damage_by_team",
    "balls_by_team",
    "frontier_by_team",
)


def _physical(run) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for ev in run.events:
        row = tuple(
            (k, v) for k, v in ev.data.items() if k not in LABEL_FIELDS
        )
        out.append((ev.kind, ev.t, row))
    return out


def _swap_one(seed: int) -> dict[str, Any]:
    """One seed, run twice, with the colours the other way round the second time.

    Ten independent checks rather than one, because they fail differently. A
    renderer that read the team would break `physical_events_equal`; a scheduler
    that broke ties on the team would break `state_digest_equal`; a start-state
    builder that consulted the team would break both *and* `duration_equal`.
    """
    plain = simulate(seed, _CONFIG)
    swapped = simulate(seed, _CONFIG.replace(team_swap=True))
    teams_plain = [b.team_id for b in plain.balls]
    teams_swapped = [b.team_id for b in swapped.balls]
    mirrored = (
        len(teams_plain) == len(teams_swapped)
        and all(a != b for a, b in zip(teams_plain, teams_swapped))
    )
    return {
        "seed": seed,
        "state_digest_equal": plain.state_digest() == swapped.state_digest(),
        "team_digest_differs": plain.team_digest() != swapped.team_digest(),
        "labels_mirrored": mirrored,
        "physical_events_equal": _physical(plain) == _physical(swapped),
        "event_count_equal": len(plain.events) == len(swapped.events),
        "duration_equal": plain.duration == swapped.duration,
        "escape_ball_equal": plain.escape_ball == swapped.escape_ball,
        "winner_flipped": (
            plain.winner_team is None and swapped.winner_team is None
        ) or (
            plain.winner_team is not None
            and swapped.winner_team is not None
            and plain.winner_team != swapped.winner_team
        ),
        "damage_swapped": list(plain.team_damage) == list(reversed(swapped.team_damage)),
        "population_swapped": list(plain.team_balls) == list(reversed(swapped.team_balls)),
    }


def fairness(config: MultishellConfig, seeds: Sequence[int], workers: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init, initargs=(config.as_dict(),)
    ) as pool:
        for row in pool.map(_swap_one, seeds, chunksize=16):
            rows.append(row)
    keys = [k for k in rows[0] if k != "seed"]
    failures = {k: [r["seed"] for r in rows if not r[k]] for k in keys}
    return {
        "kind": "category3_two_team_label_swap",
        "config_digest": config.digest(),
        "physics_digest": config.physics_digest(),
        "swapped_physics_digest": config.replace(team_swap=True).physics_digest(),
        "seeds": len(rows),
        "checks": keys,
        "all_pass": all(not v for v in failures.values()),
        "failures": {k: v[:20] for k, v in failures.items() if v},
        "failure_counts": {k: len(v) for k, v in failures.items()},
    }


# --------------------------------------------------------------------------
# Shortlist
# --------------------------------------------------------------------------

#: The named selection rule.
#:
#: **Nothing here prefers a close finish.** There is no line on
#: `win_margin_seconds`, none on `population_lead_changes` and none on the
#: final gap. The three race lines ask only whether the second colour was in
#: the race - that it reproduced, that it got past the third shell, and that it
#: was not reduced to a passenger - because a rule that rewarded a narrow finish
#: would become, one sweep later, a rule that selects for arranged ones.
SHORTLIST_RULE: dict[str, Any] = {
    "duration_seconds": [20.0, 26.0],
    "first_spawn_seconds_preferred_max": 2.0,
    "first_spawn_seconds_reject_above": 3.0,
    "min_population": 12,
    "min_team_population": 4,
    "min_loser_frontier": 3,
    "max_winner_population_share": 0.75,
    "min_breaks": 6,
    "max_collision_rate": 18.0,
    "flags": "none",
}


def _bucket(row: dict[str, Any]) -> tuple[str, str, str]:
    """The variety key: who won, from what generation, through what."""
    race = row["race"]
    winner = race["winner_name"] or "none"
    who = "founder" if (race["winner_generation"] or 0) == 0 else "descendant"
    route = race["winner_route"] or "none"
    return (winner, who, route)


def shortlist(rows: Sequence[dict[str, Any]], take: int = 20) -> dict[str, Any]:
    rule = SHORTLIST_RULE
    lo, hi = rule["duration_seconds"]
    eligible: list[dict[str, Any]] = []
    for row in rows:
        if not row["escaped"] or row["flags"]:
            continue
        if not lo <= row["duration"] <= hi:
            continue
        first = row["first_spawn"]
        if first is None or first > rule["first_spawn_seconds_reject_above"]:
            continue
        race = row["race"]
        if row["population_total"] < rule["min_population"]:
            continue
        if min(race["population_by_team"]) < rule["min_team_population"]:
            continue
        if (race["loser_frontier"] or 0) < rule["min_loser_frontier"]:
            continue
        if (race["population_share_winner"] or 1.0) > rule["max_winner_population_share"]:
            continue
        if row["breaks"] < rule["min_breaks"]:
            continue
        if row["collision_rate"] > rule["max_collision_rate"]:
            continue
        eligible.append(row)

    # Variety first, then the two things the brief calls out as production
    # quality: an early first clone and a big but readable population.
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in eligible:
        buckets.setdefault(_bucket(row), []).append(row)
    for group in buckets.values():
        group.sort(
            key=lambda r: (
                r["first_spawn"] > rule["first_spawn_seconds_preferred_max"],
                -r["population_total"],
                r["collision_rate"],
                r["seed"],
            )
        )

    # Round-robin over the buckets rather than taking the best N overall, so a
    # crowded bucket cannot squeeze out the one founder win or the one break
    # route in the batch.
    picked: list[dict[str, Any]] = []
    used: set[int] = set()
    depth = 0
    order = sorted(buckets)
    while len(picked) < take:
        added = False
        for key in order:
            group = buckets[key]
            if depth < len(group) and group[depth]["seed"] not in used:
                picked.append(group[depth])
                used.add(group[depth]["seed"])
                added = True
                if len(picked) >= take:
                    break
        if not added:
            break
        depth += 1
    picked.sort(key=lambda r: (-r["population_total"], r["duration"]))
    # The field names are the ones `satisfying.multishell_visual.candidate_seeds`
    # reads, so the review set is chosen here and applied there without a
    # translation step in between that could disagree with either.
    return {
        "kind": "category3_two_team_shortlist",
        "rule": rule,
        "eligible": len(eligible),
        "buckets": {"/".join(k): len(v) for k, v in sorted(buckets.items())},
        "seeds": [r["seed"] for r in eligible],
        "review_seeds": [r["seed"] for r in picked],
        "candidates": picked,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write(payload: Any, path: str | os.PathLike[str] | None) -> None:
    if path is None:
        print(json.dumps(payload, indent=1, default=str))
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8")
    print("->", target)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    batch = sub.add_parser("batch", help="run a seed block and summarise it")
    batch.add_argument("--count", type=int, default=20_000)
    batch.add_argument("--start", type=int, default=1)
    batch.add_argument("--workers", type=int, default=11)
    batch.add_argument("--out", type=Path)
    batch.add_argument("--records", type=Path)

    swap = sub.add_parser("fairness", help="the label-swap invariance test")
    swap.add_argument("--count", type=int, default=400)
    swap.add_argument("--start", type=int, default=1)
    swap.add_argument("--workers", type=int, default=11)
    swap.add_argument("--out", type=Path)

    short = sub.add_parser("shortlist", help="apply the selection rule to records")
    short.add_argument("--records", type=Path, required=True)
    short.add_argument("--take", type=int, default=20)
    short.add_argument("--out", type=Path)

    args = parser.parse_args(argv)
    config = DEFAULT_CONFIG

    if args.command == "batch":
        seeds = range(args.start, args.start + args.count)
        records = run_batch(seeds, config, DEFAULT_THRESHOLDS, workers=args.workers)
        summary = summarise(_rehydrate(records), DEFAULT_THRESHOLDS)
        payload = {
            "kind": "category3_two_team_batch",
            "config": config.as_dict(),
            "config_digest": config.digest(),
            "physics_digest": config.physics_digest(),
            "difficulty": difficulty_profile(config),
            "thresholds": DEFAULT_THRESHOLDS.as_dict(),
            "seed_start": args.start,
            "seed_count": args.count,
            "summary": summary,
        }
        _write(payload, args.out)
        if args.records:
            _write(
                {
                    "seed_start": args.start,
                    "seed_count": args.count,
                    "config_digest": config.digest(),
                    "rows": records,
                },
                args.records,
            )
        print(json.dumps({
            "escape_rate": summary["escape_rate"],
            "usable_rate": summary["usable_rate"],
            "pass_rate_by_shell": summary["pass_rate_by_shell"],
            "population_total": summary["population_total"],
            "wins_by_team": summary["race"]["wins_by_team"],
            "team_win_z": summary["race"]["team_win_z"],
            "wins_by_founder_slot": summary["race"]["wins_by_founder_slot"],
            "slot_win_z": summary["race"]["slot_win_z"],
        }, indent=1, default=str))
        return 0

    if args.command == "fairness":
        seeds = range(args.start, args.start + args.count)
        payload = fairness(config, seeds, args.workers)
        _write(payload, args.out)
        print(json.dumps(
            {k: payload[k] for k in ("seeds", "all_pass", "failure_counts")}, indent=1))
        return 0

    if args.command == "shortlist":
        blob = json.loads(Path(args.records).read_text(encoding="utf-8"))
        payload = shortlist(blob["rows"], args.take)
        payload["config_digest"] = blob.get("config_digest")
        _write(payload, args.out)
        print(json.dumps({"eligible": payload["eligible"],
                          "review_seeds": payload["review_seeds"],
                          "buckets": payload["buckets"]}, indent=1))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

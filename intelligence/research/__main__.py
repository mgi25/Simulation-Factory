"""The research store from a terminal, with no Python in between.

    python -m intelligence.research list
    python -m intelligence.research list --kind opportunity
    python -m intelligence.research show opportunity marble-elimination-format
    python -m intelligence.research thread yt-competitor-marble-run
    python -m intelligence.research rank --rubric opportunity-v1
    python -m intelligence.research check --today 2026-09-16

`check` runs the integrity sweep and the staleness sweep and exits non-zero if
either finds something, so it can become a pre-merge step later without
changing shape. `rank` prints the weighted totals with their coverage and the
caveat, because a ranking printed without the caveat is the failure mode the
scoring module exists to prevent.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from ai_platform.serde import dumps
from intelligence.research.errors import ResearchError
from intelligence.research.scoring import CAVEAT, OpportunityScorecard, ScoringRubric, rank, score_opportunity
from intelligence.research.store import DEFAULT_ROOT, RECORD_TYPES, ResearchStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="intelligence.research")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="research record directory")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="record ids, by kind")
    listing.add_argument("--kind", choices=sorted(RECORD_TYPES), default=None)

    show = sub.add_parser("show", help="one record as canonical JSON")
    show.add_argument("kind", choices=sorted(RECORD_TYPES))
    show.add_argument("id")

    thread = sub.add_parser("thread", help="a source and everything downstream of it")
    thread.add_argument("source_id")

    ranking = sub.add_parser("rank", help="score every scorecard against one rubric")
    ranking.add_argument("--rubric", required=True)

    check = sub.add_parser("check", help="integrity and staleness; non-zero if anything is wrong")
    check.add_argument("--today", default="", help="ISO date for the staleness sweep")
    return parser


def _today(value: str) -> dt.date:
    return dt.date.fromisoformat(value) if value else dt.date.today()


def _cmd_list(store: ResearchStore, kind: str | None) -> int:
    records = store.load_all(kind)
    if not records:
        print("(no records)")
        return 0
    for record in records:
        title = getattr(record, "title", "") or getattr(record, "purpose", "")
        stage = getattr(record, "stage", None)
        suffix = f"  [{stage.value}]" if stage is not None else ""
        print(f"{record.kind:<15} {record.id:<40} {title}{suffix}")
    return 0


def _cmd_rank(store: ResearchStore, rubric_id: str) -> int:
    rubric: ScoringRubric = store.get(ScoringRubric.kind, rubric_id)
    cards = [
        c for c in store.load_all(OpportunityScorecard.kind) if c.rubric_id == rubric_id
    ]
    if not cards:
        print(f"(no scorecards against rubric {rubric_id!r})")
        return 0
    results = rank(score_opportunity(rubric, card) for card in cards)
    width = max(len(r.opportunity_id) for r in results)
    for result in results:
        gaps = (
            f"  missing: {', '.join(result.missing_dimensions)}"
            if result.missing_dimensions
            else ""
        )
        print(
            f"{result.weighted_total:>8.3f}  {result.opportunity_id:<{width}}  "
            f"coverage {result.weight_covered:.0%}{gaps}"
        )
    print()
    print(CAVEAT)
    return 0


def _cmd_check(store: ResearchStore, today: dt.date) -> int:
    issues = store.integrity()
    stale = store.stale(today)
    for issue in issues:
        print(f"INTEGRITY  {issue}")
    for record in stale:
        due = record.confidence.recheck_on
        print(f"STALE      {record.kind}/{record.id} due {due}")
    if not issues and not stale:
        print("ok")
        return 0
    print(f"\n{len(issues)} integrity issue(s), {len(stale)} stale record(s)")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ResearchStore(args.root)
    try:
        if args.command == "list":
            return _cmd_list(store, args.kind)
        if args.command == "show":
            print(dumps(store.get(args.kind, args.id)), end="")
            return 0
        if args.command == "thread":
            print(dumps(store.thread(args.source_id)), end="")
            return 0
        if args.command == "rank":
            return _cmd_rank(store, args.rubric)
        if args.command == "check":
            return _cmd_check(store, _today(args.today))
    except ResearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

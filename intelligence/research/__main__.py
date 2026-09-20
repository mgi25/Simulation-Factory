"""The research store from a terminal, with no Python in between.

    python -m intelligence.research list
    python -m intelligence.research list --kind opportunity
    python -m intelligence.research show opportunity marble-elimination-format
    python -m intelligence.research thread yt-competitor-marble-run
    python -m intelligence.research rank --rubric opportunity-v1
    python -m intelligence.research check --today 2026-09-16

and the discovery queue in front of them:

    python -m intelligence.research ingest captured.json --by research_lead
    python -m intelligence.research candidates --state queued
    python -m intelligence.research screen <id> --to screened_in --by X --reason "..."
    python -m intelligence.research promote <id> --spec promotion.json
    python -m intelligence.research funnel

and the batch layer that decides how many of them are worth paying for:

    python -m intelligence.research batch show <id>
    python -m intelligence.research batch report <id> --today 2026-09-16
    python -m intelligence.research batch queue <id>

`check` runs the integrity sweep and the staleness sweep and exits non-zero if
either finds something, so it can become a pre-merge step later without
changing shape. `rank` prints the weighted totals with their coverage and the
caveat, because a ranking printed without the caveat is the failure mode the
scoring module exists to prevent.

`promote` takes a `--spec` file and has no flags for confidence or rights. That
is not terseness: a `ResearchConfidence` is a level, a basis and the observation
that would overturn it, and a command line that let a researcher skip those
would be a command line that manufactures them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from pathlib import Path

from ai_platform.serde import dumps, read_json
from intelligence.research.common import ResearchConfidence
from intelligence.research.discovery import CandidateState, DiscoveryCandidate, screen_candidate
from intelligence.research.errors import ResearchError
from intelligence.research.funnel import describe_funnel
from intelligence.research.ingestion import ingest_envelope, load_envelopes
from intelligence.research.scoring import CAVEAT, OpportunityScorecard, ScoringRubric, rank, score_opportunity
from intelligence.research.sources import RightsStatus, SourceType
from intelligence.research.batch import ResearchBatch
from intelligence.research.screening_queue import QUEUE_CAVEAT
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

    ingest = sub.add_parser("ingest", help="load captured metadata from a JSON file")
    ingest.add_argument("path", help="a JSON envelope, or a list of them")
    ingest.add_argument("--by", required=True, help="who captured this metadata")
    ingest.add_argument("--query", default="", help="discovery query id, if not in the file")

    candidates = sub.add_parser("candidates", help="the discovery queue")
    candidates.add_argument(
        "--state", choices=[s.value for s in CandidateState], default=None
    )

    screen = sub.add_parser("screen", help="record a screening decision")
    screen.add_argument("candidate_id")
    screen.add_argument("--to", required=True, choices=[s.value for s in CandidateState])
    screen.add_argument("--by", required=True, help="who is deciding")
    screen.add_argument("--reason", required=True, help="why")
    screen.add_argument("--on", default="", help="ISO date; defaults to today")

    promote = sub.add_parser("promote", help="turn a screened-in candidate into a source")
    promote.add_argument("candidate_id")
    promote.add_argument("--spec", default="", help="JSON: source_id, confidence, rights")

    sub.add_parser("funnel", help="the cost tiers, cheapest first")

    batch = sub.add_parser("batch", help="a research batch: its cost, coverage and stops")
    batch_sub = batch.add_subparsers(dest="batch_command", required=True)
    batch_show = batch_sub.add_parser("show", help="the plan, the log and the history")
    batch_show.add_argument("id")
    batch_report = batch_sub.add_parser("report", help="the whole batch as numbers")
    batch_report.add_argument("id")
    batch_report.add_argument("--today", default="", help="ISO date the report is as of")
    batch_queue = batch_sub.add_parser("queue", help="the screening queue, best first")
    batch_queue.add_argument("id")
    return parser


def _today(value: str) -> dt.date:
    return dt.date.fromisoformat(value) if value else dt.date.today()


def _label(record) -> str:
    for field in ("title", "purpose", "objective", "canonical_url"):
        value = getattr(record, field, "")
        if value:
            return value
    return ""


def _cmd_list(store: ResearchStore, kind: str | None) -> int:
    records = store.load_all(kind)
    if not records:
        print("(no records)")
        return 0
    for record in records:
        position = getattr(record, "stage", None) or getattr(record, "state", None)
        suffix = f"  [{position.value}]" if position is not None else ""
        print(f"{record.kind:<20} {record.id:<40} {_label(record)}{suffix}")
    return 0


def _cmd_ingest(store: ResearchStore, path: str, by: str, query: str) -> int:
    """The manual adapter, end to end: a JSON file becomes queued candidates."""
    for envelope in load_envelopes(path):
        ingested = ingest_envelope(envelope, discovered_by=by, query_id=query)
        outcome = store.ingest(ingested.candidate, ingested.snapshot)
        reading = "reading recorded" if outcome.snapshot_added else "no new reading"
        print(f"{outcome.action:<7} {outcome.candidate.id}  {reading}")
        for conflict in outcome.conflicts:
            print(f"        conflict kept unresolved: {conflict}")
    return 0


def _cmd_candidates(store: ResearchStore, state: str | None) -> int:
    wanted = CandidateState(state) if state else None
    records = store.candidates(wanted)
    if not records:
        print("(no candidates)")
        return 0
    for candidate in records:
        unknown = (
            f"  unknown: {', '.join(candidate.unknown_fields)}"
            if candidate.unknown_fields
            else ""
        )
        print(
            f"{candidate.state.value:<20} {candidate.id:<44} "
            f"{candidate.title or candidate.canonical_url}{unknown}"
        )
    return 0


def _cmd_screen(
    store: ResearchStore, candidate_id: str, to: str, by: str, reason: str, on: str
) -> int:
    candidate = store.get(DiscoveryCandidate.kind, candidate_id)
    updated = screen_candidate(
        candidate, CandidateState(to), on=_today(on), by=by, reason=reason
    )
    store.add(updated, overwrite=True)
    print(f"{candidate.state.value} -> {updated.state.value}  {updated.id}")
    return 0


def _cmd_promote(store: ResearchStore, candidate_id: str, spec_path: str) -> int:
    if not spec_path:
        raise ResearchError(
            "promote needs --spec: a JSON file with source_id, source_type, rights, "
            "reason, promoted_by and a confidence block. A source carries a research "
            "confidence - a level, a basis, and what would overturn it - and those are "
            "judgements, not flags a command line should default for you."
        )
    spec = read_json(Path(spec_path))
    result = store.promote(
        candidate_id,
        source_id=spec["source_id"],
        source_type=SourceType(spec["source_type"]),
        rights=RightsStatus(spec.get("rights", "link_only")),
        confidence=ResearchConfidence.from_dict(spec["confidence"]),
        promoted_by=spec["promoted_by"],
        on=_today(spec.get("on", "")),
        reason=spec["reason"],
        title=spec.get("title", ""),
        notes=spec.get("notes", ""),
    )
    print(f"promoted {result.candidate.id} -> source/{result.source.id}")
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


def _cmd_batch_show(store: ResearchStore, batch_id: str) -> int:
    """The plan and the log. Deliberately not the report - this is what was
    agreed and what happened, with no derived numbers to argue with."""
    batch = store.get(ResearchBatch.kind, batch_id)
    print(f"{batch.id}  {batch.status.value}")
    print(f"  objective   {batch.objective}")
    print(f"  owner       {batch.owner}   planned {batch.created}")
    if batch.target is not None:
        print(f"  target      {batch.target.minimum}-{batch.target.maximum} candidates")
    print(f"  queries     {', '.join(batch.query_ids)}")
    if batch.unrun_query_ids:
        print(f"  never run   {', '.join(batch.unrun_query_ids)}")
    print("  budget")
    for name, limit in batch.budget.limits:
        print(f"    {name:<28} {limit}")
    if batch.budget.deadline is not None:
        print(f"    {'deadline':<28} {batch.budget.deadline}")
    print("  stop conditions")
    for condition in batch.stop_conditions:
        detail = condition.threshold or condition.deadline or ""
        if condition.saturation is not None:
            rule = condition.saturation
            detail = f"{rule.rounds} rounds under {rule.new_rate_below} {rule.metric.value}"
        print(f"    {condition.reason.value:<28} [{condition.action.value}] {detail}")
    print(f"  rounds      {len(batch.rounds)}, {batch.observations} observation(s), "
          f"{len(batch.candidate_ids)} unique")
    for index, entry in enumerate(batch.rounds):
        print(f"    {index:>3}  {entry.ran_on}  {entry.query_id:<28} "
              f"{entry.observations} observation(s)")
    print("  history")
    for event in batch.history:
        print(f"    {event.on}  {event.kind.value:<16} {event.by:<24} {event.detail}")
    return 0


def _cmd_batch_report(store: ResearchStore, batch_id: str, today: dt.date) -> int:
    """Non-zero when a declared stop condition has fired or a ceiling is over."""
    report = store.batch_report(batch_id, as_of=today)
    for line in report.lines():
        print(line)
    return 1 if (report.halting or report.exceeded) else 0


def _cmd_batch_queue(store: ResearchStore, batch_id: str) -> int:
    entries = store.batch_queue(batch_id)
    if not entries:
        print("(no candidate is awaiting a screening decision)")
        return 0
    width = max(len(entry.candidate_id) for entry in entries)
    for entry in entries:
        mean = "  n/a" if entry.signal_mean is None else f"{entry.signal_mean:5.2f}"
        missing = (
            f"  missing: {', '.join(entry.missing_signals)}"
            if entry.missing_signals
            else ""
        )
        print(
            f"{mean}  {entry.status.value:<17} {entry.candidate_id:<{width}}  "
            f"{entry.state.value:<12} {entry.recommendation.value}{missing}"
        )
    print()
    print(QUEUE_CAVEAT)
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
        if args.command == "ingest":
            return _cmd_ingest(store, args.path, args.by, args.query)
        if args.command == "candidates":
            return _cmd_candidates(store, args.state)
        if args.command == "screen":
            return _cmd_screen(
                store, args.candidate_id, args.to, args.by, args.reason, args.on
            )
        if args.command == "promote":
            return _cmd_promote(store, args.candidate_id, args.spec)
        if args.command == "funnel":
            for line in describe_funnel():
                print(line)
            return 0
        if args.command == "batch":
            if args.batch_command == "show":
                return _cmd_batch_show(store, args.id)
            if args.batch_command == "report":
                return _cmd_batch_report(store, args.id, _today(args.today))
            if args.batch_command == "queue":
                return _cmd_batch_queue(store, args.id)
    except ResearchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

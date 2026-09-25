"""The experience store from the command line.

    python -m company.experience capture --state-dir S --repo-root R [--work-order WO ...]
    python -m company.experience suggest --work-order WO --state-dir S --repo-root R
    python -m company.experience list    --state-dir S
    python -m company.experience show    --experience-id ID --state-dir S

`--state-dir` is never defaulted, for the reason `company.engineering` gives:
a command that picks its own directory writes history somewhere nobody looks.
The experience store lives beside the engineering history it indexes.

## `suggest` is the one a runner calls, and it cannot fail the job

It first indexes every settled attempt in the state directory (idempotently -
nothing already stored is rewritten; `--no-capture` skips this), then answers
for one work order with the advisory artifact on stdout. Exit codes:

    0  an advisory was produced - a precedent, an abstention, or an
       "experience unavailable" abstention when the store itself failed
    2  the request was malformed: no such work order, or one that no longer
       decodes, so no query can be built

A broken or empty experience store is exit 0 with an abstention, never an
error: experience is an optimisation, and an optimisation that could stop the
work it optimises would have become a dependency.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any

from company.engineering.store import EngineeringStore
from company.runtime.execution_store import ExecutionStore
from company.validation.errors import CompanyOSError

from .advice import build_advice, unavailable_advice
from .capture import capture_settled, governance_facts, governed_class
from .repository import RepositoryView
from .retrieval import ExperienceQuery, retrieve
from .store import ExperienceStore


def _day(value: str | None) -> dt.date:
    return dt.date.fromisoformat(value) if value else dt.date.today()


def _emit(payload: Any) -> None:
    # ASCII-escaped, as `company.engineering` emits: a review summary can hold
    # any character, and a Windows pipe's code page cannot encode all of them.
    print(json.dumps(payload, sort_keys=True, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m company.experience")
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture", help="index every settled attempt in a state directory")
    capture.add_argument("--state-dir", required=True)
    capture.add_argument("--repo-root", required=True)
    capture.add_argument("--work-order", action="append", default=None)
    capture.add_argument("--on", default=None, help="capture date (ISO); defaults to today")

    suggest = sub.add_parser("suggest", help="the advisory for one work order")
    suggest.add_argument("--state-dir", required=True)
    suggest.add_argument("--repo-root", required=True)
    suggest.add_argument("--work-order", required=True)
    suggest.add_argument("--on", default=None)
    suggest.add_argument("--no-capture", action="store_true")
    suggest.add_argument("--json", action="store_true", help="accepted for symmetry; output is always JSON")

    listing = sub.add_parser("list", help="every stored episode, one line each")
    listing.add_argument("--state-dir", required=True)

    show = sub.add_parser("show", help="one stored episode")
    show.add_argument("--state-dir", required=True)
    show.add_argument("--experience-id", required=True)
    return parser


def _current_attempt(state_dir: Path, work_order_id: str, job: Any) -> int:
    """The attempt being decided: the latest packet while developing, else the next."""
    try:
        packets = len(ExecutionStore(state_dir).packet_records(work_order_id))
    except Exception:  # noqa: BLE001 - the attempt number is a feature, not a gate
        packets = job.developer_attempts if job is not None else 0
    developing = job is not None and job.state.value == "developing"
    return max(1, packets if developing else packets + 1)


def _suggest(args: argparse.Namespace) -> int:
    state_dir = Path(args.state_dir).resolve()
    on = _day(args.on)
    engineering = EngineeringStore(state_dir)
    try:
        order = engineering.work_order(args.work_order)
        job = engineering.job(args.work_order)
    except Exception as exc:  # noqa: BLE001 - no query can be built from this
        sys.stderr.write(f"work order {args.work_order} cannot be read: {exc}\n")
        return 2
    if order is None:
        sys.stderr.write(f"no work order {args.work_order} is stored in {state_dir}\n")
        return 2
    attempt = _current_attempt(state_dir, args.work_order, job)
    try:
        view = RepositoryView.load(args.repo_root)
        store = ExperienceStore(state_dir)
        capture_counts: dict[str, int] = {}
        if not args.no_capture:
            capture_counts = capture_settled(state_dir, view, captured_on=on, store=store).counts()
        query = ExperienceQuery.from_work_order(order, attempt=attempt)
        result = retrieve(
            query,
            view,
            scan=store.scan(),
            resolve_source=lambda label: state_dir if label == "local" else None,
        )
        advice = build_advice(
            query, result, view, work_order_fingerprint=order.fingerprint(), as_of=on, capture=capture_counts
        )
    except Exception as exc:  # noqa: BLE001 - degrade to "no precedent", never fail
        advice = unavailable_advice(
            order.work_order_id, order.fingerprint(), attempt, as_of=on, reason=f"{type(exc).__name__}: {exc}"
        )
    _emit(advice)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capture":
            view = RepositoryView.load(args.repo_root)
            report = capture_settled(
                args.state_dir, view, captured_on=_day(args.on), work_order_ids=args.work_order
            )
            _emit(report.to_dict())
            return 0
        if args.command == "suggest":
            return _suggest(args)
        store = ExperienceStore(args.state_dir)
        if args.command == "list":
            scan = store.scan()
            rows = []
            for episode in scan.episodes:
                facts = governance_facts(store.state_dir, episode)
                klass, _reasons = governed_class(episode, facts) if facts.available else (episode.engineering_class(), ())
                rows.append(
                    {
                        "experience_id": episode.experience_id,
                        "work_order_id": episode.work_order_id,
                        "attempt": episode.packet_attempt,
                        "settled_on": episode.settled_on.isoformat(),
                        "class": klass.value,
                        "source": episode.source,
                    }
                )
            _emit({"episodes": rows, "problems": list(scan.problems)})
            return 0
        episode = store.get(args.experience_id)
        if episode is None:
            sys.stderr.write(f"no episode {args.experience_id} is stored\n")
            return 2
        _emit(episode.to_dict())
        return 0
    except CompanyOSError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

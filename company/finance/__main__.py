"""A command line over recorded financial state. Five readers and one writer.

    ledger              every money-bearing record in the order it was written
    list KIND           the records of one kind, as canonical JSON
    budget BUDGET_ID    consumption, with unknown reported as unknown
    reserved            what permissions.yaml currently reserves for paid spend
    integrity           every cross-record invariant over a state directory
    usage-cost          price a usage history against a supplied rate card

The commands that would move money are absent on purpose. There is no `pay`, no
`approve`, no `subscribe` - a CLI verb is exactly the affordance that turns a
proposal into an action by accident, and section 12 says finance must not
execute payment, create a subscription or change a permission.

`usage-cost` is the one command that can write, and it takes two explicit steps
to do it: without `--commit` it reports and writes nothing, and `--dry-run`
refuses to write even then. What it writes is `CostRecord`s derived from usage
that was already measured and a rate card somebody already supplied - it prices
history, it does not authorise spend.

It also cannot invent a price. `--rate-card` is required, `--provider` is
required, and a quantity the card does not cover comes back unpriced rather than
zero.

`budget` takes `--complete` because consumption over an unasserted cost set is
unknown rather than zero. Without the flag the command says so, which is the
honest answer and the one section 15 asks for.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from ai_platform.serde import dumps
from company.runtime.config import load_company_config
from company.runtime.execution_store import ExecutionStore
from company.runtime.state_paths import sequence_of
from company.runtime.usage_store import ResourceUsageStore
from knowledge.company_os.records import Evidence

from .budget import consumption
from .common import SubjectKind, SubjectRef
from .errors import FinanceError
from .integrity import check_integrity
from .proposals import PAID_SPEND_RESERVED_ACTION, unreserved_action
from .rates import load_rate_card
from .store import FinanceStore, FinanceStoreError, _KINDS
from .usage_cost import (
    AttributionScope,
    attribute_usage_costs,
    commit_attribution_costs,
    dogfood_report,
    observe_usage,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m company.finance",
        description="Read-only questions about recorded costs, revenue and budgets.",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help="directory holding finance state; required by every command but 'reserved'",
    )
    parser.add_argument(
        "--config-dir", default=None, help="directory holding the bootstrap YAML"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ledger", help="money-bearing records in write order")

    listing = sub.add_parser("list", help="every record of one kind")
    listing.add_argument("kind", choices=sorted(_KINDS))

    budget = sub.add_parser("budget", help="consumption of one budget line")
    budget.add_argument("budget_id")
    budget.add_argument(
        "--complete",
        action="store_true",
        help="assert every cost in scope is recorded; without it consumption is unknown",
    )

    sub.add_parser("reserved", help="what permissions.yaml reserves for paid spend")

    integrity = sub.add_parser(
        "integrity", help="cross-record invariants over the state directory"
    )
    integrity.add_argument(
        "--external-ref",
        action="append",
        default=None,
        metavar="ID",
        help=(
            "a subject id naming somebody else's video or channel; repeatable. "
            "Without it, revenue misattributed to a competitor cannot be checked"
        ),
    )

    usage = sub.add_parser(
        "usage-cost", help="price a resource usage history against a rate card"
    )
    usage.add_argument(
        "--usage-state",
        required=True,
        help="runtime state directory holding the resource_usage/ history",
    )
    usage.add_argument(
        "--rate-card",
        required=True,
        help="JSON file of CostRate records; there is no default and no fetch",
    )
    usage.add_argument(
        "--provider",
        required=True,
        help="whose price list applies; the usage record does not carry one",
    )
    usage.add_argument(
        "--subject",
        required=True,
        metavar="KIND:ID",
        help="what the cost is for, e.g. video:race_short_014",
    )
    usage.add_argument(
        "--measured-on",
        required=True,
        metavar="YYYY-MM-DD",
        help="the day the rate in force applies to; historical usage takes its own day",
    )
    usage.add_argument(
        "--task",
        action="append",
        default=None,
        metavar="TASK_ID",
        help="restrict to one task; repeatable. Default is every task in the history",
    )
    usage.add_argument(
        "--execution-state",
        default=None,
        help=(
            "state directory holding execution receipts, read for the executor hint. "
            "Metadata only: no arithmetic depends on it"
        ),
    )
    usage.add_argument(
        "--include-duration",
        action="store_true",
        help="price wall-clock seconds too; correct only when compute is rented by time",
    )
    usage.add_argument(
        "--scope",
        choices=[item.value for item in AttributionScope],
        default=AttributionScope.ALL_ATTEMPTS.value,
        help="which attempts the cost-per-accepted numerator includes",
    )
    usage.add_argument(
        "--accepted-deliverables",
        type=int,
        default=None,
        help="accepted deliverable count, when it is not one per accepted task",
    )
    usage.add_argument(
        "--commit",
        action="store_true",
        help="write the priced attributions as CostRecords into --state-dir",
    )
    usage.add_argument(
        "--recorded-by",
        default=None,
        help="who ran the attribution; required by --commit",
    )
    usage.add_argument(
        "--allow-restatement",
        action="store_true",
        help=(
            "record a superseding cost where a committed one was priced differently. "
            "Without it a changed price is reported and not written"
        ),
    )
    usage.add_argument(
        "--dry-run",
        action="store_true",
        help="report what --commit would write, and write nothing",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "reserved":
            return _reserved(args)
        if args.state_dir is None:
            print(f"{args.command}: --state-dir is required", file=sys.stderr)
            return 2
        store = FinanceStore(args.state_dir)
        if args.command == "ledger":
            print(dumps(store.ledger()), end="")
        elif args.command == "list":
            print(dumps([record.to_dict() for record in store.list(args.kind)]), end="")
        elif args.command == "budget":
            return _budget(store, args)
        elif args.command == "integrity":
            return _integrity(store, args)
        elif args.command == "usage-cost":
            return _usage_cost(store, args)
    except (FinanceError, FinanceStoreError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _reserved(args: argparse.Namespace) -> int:
    permissions = load_company_config(args.config_dir).permissions
    missing = unreserved_action(permissions)
    print(
        dumps(
            {
                "action": PAID_SPEND_RESERVED_ACTION,
                "reserved": not missing,
                "ceo_reserved": list(permissions.get("ceo_reserved", ())),
            }
        ),
        end="",
    )
    return 1 if missing else 0


def _budget(store: FinanceStore, args: argparse.Namespace) -> int:
    line = store.get("budget", args.budget_id)
    result = consumption(line, store.list("cost"), costs_are_complete=args.complete)
    print(dumps(result.to_dict()), end="")
    return 0


def _integrity(store: FinanceStore, args: argparse.Namespace) -> int:
    problems = check_integrity(
        costs=store.list("cost"),
        adjustments=store.list("cost_adjustment"),
        revenue=store.list("revenue"),
        rates=store.list("rate"),
        budgets=store.list("budget"),
        mappings=store.list("resource_cost_mapping"),
        investments=store.list("reusable_investment"),
        reuse_events=store.list("reuse_event"),
        proposals=store.list("spend_proposal"),
        decisions=store.list("spend_decision"),
        external_reference_ids=args.external_ref,
        permissions=load_company_config(args.config_dir).permissions,
    )
    for problem in problems:
        print(problem)
    return 1 if problems else 0


def _subject(text: str) -> SubjectRef:
    kind, _, identifier = text.partition(":")
    if not identifier:
        raise FinanceError(
            f"--subject {text!r} must read KIND:ID, e.g. video:race_short_014. Known "
            "kinds: " + ", ".join(sorted(item.value for item in SubjectKind))
        )
    try:
        return SubjectRef(kind=SubjectKind(kind), id=identifier)
    except ValueError as exc:
        raise FinanceError(f"--subject {text!r}: {exc}") from exc


def _executor_hints(state_dir: str | None, task_id: str, usage_count: int) -> dict[int, str]:
    """Attempt number to executor hint, and nothing when the histories disagree.

    The usage history and the receipt history are numbered independently. They
    line up whenever every attempt produced one of each, which is the normal
    path; when the counts differ they may not, and a provenance claim that might
    be joined wrongly is worse than one that is absent. So the join is refused
    rather than guessed.
    """
    if state_dir is None:
        return {}
    attempts = ExecutionStore(state_dir).attempts(task_id)
    if not attempts or len(attempts) != usage_count:
        return {}
    return {
        item.attempt: getattr(item.receipt.executor, "value", item.receipt.executor)
        for item in attempts
    }


def _usage_cost(store: FinanceStore, args: argparse.Namespace) -> int:
    """Price a usage history, report it, and write only when told to twice."""
    if args.commit and not args.recorded_by:
        raise FinanceError("--commit needs --recorded-by: a cost record names who filed it")
    subject = _subject(args.subject)
    card = load_rate_card(args.rate_card)
    usage_store = ResourceUsageStore(args.usage_state)
    task_ids = (
        tuple(args.task)
        if args.task
        else tuple(sorted({record.task_id for record in usage_store.records()}))
    )
    observations = []
    for task_id in task_ids:
        records = usage_store.records(task_id)
        pointers = usage_store.pointers(task_id)
        if len(records) != len(pointers):  # pragma: no cover - same directory listing
            raise FinanceError(
                f"task {task_id}: {len(records)} usage records but {len(pointers)} "
                "pointers; the history is not readable as attempts"
            )
        hints = _executor_hints(args.execution_state, task_id, len(records))
        for record, pointer in zip(records, pointers):
            attempt = sequence_of(pathlib.Path(pointer.record_ref))
            observations.append(
                observe_usage(
                    record,
                    usage_ref=pointer.record_ref,
                    usage_fingerprint=pointer.fingerprint,
                    provider=args.provider,
                    subject=subject,
                    measured_on=args.measured_on,
                    evidence=(
                        Evidence(
                            kind="measurement",
                            ref=pointer.record_ref,
                            note="immutable resource usage record",
                        ),
                    ),
                    attempt=attempt,
                    executor=hints.get(attempt, ""),
                    include_duration=args.include_duration,
                )
            )
    run = attribute_usage_costs(observations, card, as_of=args.measured_on)
    report = dogfood_report(
        run,
        scope=AttributionScope(args.scope),
        accepted_deliverables=args.accepted_deliverables,
    )
    payload = {"report": report.to_dict()}
    if args.commit:
        commit = commit_attribution_costs(
            run,
            store,
            recorded_by=args.recorded_by,
            recorded_on=args.measured_on,
            dry_run=args.dry_run,
            allow_restatement=args.allow_restatement,
        )
        payload["commit"] = commit.to_dict()
    print(dumps(payload), end="")
    return 1 if run.missing else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

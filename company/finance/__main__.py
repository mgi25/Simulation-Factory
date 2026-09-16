"""A read-only command line over recorded financial state.

Five subcommands, none of which writes anything:

    ledger              every money-bearing record in the order it was written
    list KIND           the records of one kind, as canonical JSON
    budget BUDGET_ID    consumption, with unknown reported as unknown
    reserved            what permissions.yaml currently reserves for paid spend
    integrity           every cross-record invariant over a state directory

The commands that would move money are absent on purpose. There is no `pay`, no
`approve`, no `subscribe` and no `record` - a CLI verb is exactly the affordance
that turns a proposal into an action by accident, and section 12 says finance
must not execute payment, create a subscription or change a permission.

`budget` takes `--complete` because consumption over an unasserted cost set is
unknown rather than zero. Without the flag the command says so, which is the
honest answer and the one section 15 asks for.
"""

from __future__ import annotations

import argparse
import sys

from ai_platform.serde import dumps
from company.runtime.config import load_company_config

from .budget import consumption
from .errors import FinanceError
from .integrity import check_integrity
from .proposals import PAID_SPEND_RESERVED_ACTION, unreserved_action
from .store import FinanceStore, FinanceStoreError, _KINDS


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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

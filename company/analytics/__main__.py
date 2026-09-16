"""Read-only command line. No verb here records, concludes or publishes anything.

`metrics` prints the metric definitions, which is the answer to "what does
retention mean here". `windows` prints the standard observation windows.
`report` renders the CEO page from a state directory, and `check` reports
integrity problems in one. Every subcommand reads; none writes, because
recording an observation is something a caller does with evidence in hand, not
something a terminal session does by hand.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from .integrity import CONSTRUCTION_ENFORCED, check_integrity
from .metrics import DEFAULT_REGISTRY
from .report import build_report
from .store import AnalyticsStore
from .windows import STANDARD_AGE_WINDOWS


def _metrics(args: argparse.Namespace) -> int:
    names = DEFAULT_REGISTRY.names()
    print(f"{len(names)} metric definition(s)")
    for name in names:
        definition = DEFAULT_REGISTRY.get(name)
        access = "private" if definition.private else "public"
        print(f"\n  {definition.name}  [{definition.kind.value}, {access}]")
        print(f"    unit: {definition.unit}")
        if definition.denominator:
            print(f"    per:  {definition.denominator}")
        if args.verbose:
            print(f"    {definition.definition}")
    if not args.verbose:
        print("\n(--verbose for the full definition of each)")
    return 0


def _windows(_args: argparse.Namespace) -> int:
    print(f"{len(STANDARD_AGE_WINDOWS)} standard observation window(s)")
    for window in STANDARD_AGE_WINDOWS:
        print(f"  {window}")
    print(
        "\nWindows are half-open: a reading at hour 24 belongs to the next window, "
        "not to first_24h, so no reading is counted twice."
    )
    return 0


def _rules(_args: argparse.Namespace) -> int:
    print("Refused at construction:")
    for description, exception in CONSTRUCTION_ENFORCED:
        print(f"  {description:<52} {exception.__name__}")
    return 0


def _report(args: argparse.Namespace) -> int:
    store = AnalyticsStore(args.state_dir)
    problems = check_integrity(store) if args.verbose else ()
    print(build_report(store, args.as_of or dt.date.today(), integrity_problems=problems).render())
    return 0


def _check(args: argparse.Namespace) -> int:
    problems = check_integrity(AnalyticsStore(args.state_dir))
    if not problems:
        print("no integrity problems")
        return 0
    print(f"{len(problems)} integrity problem(s)")
    for problem in problems:
        print(f"  {problem}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m company.analytics",
        description="Read-only views over analytics definitions and state.",
    )
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("metrics", help="what each metric name means").set_defaults(func=_metrics)
    sub.add_parser("windows", help="the standard observation windows").set_defaults(func=_windows)
    sub.add_parser("rules", help="what is refused at construction").set_defaults(func=_rules)

    report = sub.add_parser("report", help="render the analytics report")
    report.add_argument("state_dir")
    report.add_argument("--as-of", type=dt.date.fromisoformat, dest="as_of")
    report.set_defaults(func=_report)

    check = sub.add_parser("check", help="cross-record integrity of a state directory")
    check.add_argument("state_dir")
    check.set_defaults(func=_check)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

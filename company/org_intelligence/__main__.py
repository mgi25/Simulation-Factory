"""Read-only command line. There is no verb here that changes anything.

`python -m company.org_intelligence management` prints the structural facts of
the current org chart; `policy` prints the thresholds those facts were measured
against; `check` reports integrity problems in a state directory. No subcommand
merges, archives, reassigns or approves, because no function in this package
does.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from company.runtime.config import load_company_config

from .common import rendered_configuration
from .integrity import check_integrity
from .management import DEFAULT_MANAGEMENT_POLICY, ManagementGraph, management_signals
from .research_evidence import DEFAULT_RESEARCH_POLICY
from .resources import DEFAULT_RESOURCE_POLICY
from .store import OrgIntelligenceStore
from .window import ReviewWindow
from .workforce_evidence import DEFAULT_WORKFORCE_POLICY


def _management(args: argparse.Namespace) -> int:
    config = load_company_config()
    graph = ManagementGraph.from_org_registry(config.org_registry)
    today = dt.date.today()
    window = ReviewWindow(start=today, end=today, label="structure as it stands today")
    print(f"org chart, {len(graph.employees)} employee(s), root {graph.external_root!r}")
    for employee_id, depth in graph.depths():
        reports = graph.direct_reports(employee_id)
        shown = "none" if not reports else ", ".join(reports)
        print(
            f"  {employee_id:<34} depth {depth if depth is not None else 'in a cycle':<10} "
            f"reports: {shown}"
        )
    signals = management_signals(graph, window=window, policy=DEFAULT_MANAGEMENT_POLICY)
    print(f"\n{len(signals)} structural signal(s)")
    for signal in signals:
        print(f"  {signal.type.value:<30} {signal.detail}")
        for caveat in signal.caveats:
            print(f"      caveat: {caveat}")
    if args.verbose:
        issues = check_integrity(
            org_registry=config.org_registry, permissions=config.permissions
        )
        print(f"\n{len(issues)} integrity issue(s)")
        for issue in issues:
            print(f"  {issue}")
    return 0


def _policy(_args: argparse.Namespace) -> int:
    for name, value in rendered_configuration(
        DEFAULT_MANAGEMENT_POLICY,
        DEFAULT_WORKFORCE_POLICY,
        DEFAULT_RESOURCE_POLICY,
        DEFAULT_RESEARCH_POLICY,
    ):
        print(f"{name:<52} {value}")
    return 0


def _check(args: argparse.Namespace) -> int:
    config = load_company_config()
    store = OrgIntelligenceStore(args.state_dir)
    issues = check_integrity(
        org_registry=config.org_registry,
        permissions=config.permissions,
        reviews=store.list("review"),
        signals=store.list("signal"),
        findings=store.list("finding"),
        recommendations=store.list("recommendation"),
        change_proposals=store.list("change_proposal"),
        experiments=store.list("experiment"),
        change_reviews=store.list("change_review"),
    )
    for issue in issues:
        print(issue)
    print(f"{len(issues)} issue(s)")
    return 1 if issues else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m company.org_intelligence",
        description="Read-only organizational analysis. Nothing here changes the company.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    management = sub.add_parser("management", help="structural facts about the org chart")
    management.add_argument("--verbose", action="store_true", help="also run integrity checks")
    management.set_defaults(handler=_management)

    policy = sub.add_parser("policy", help="every threshold this package would use")
    policy.set_defaults(handler=_policy)

    check = sub.add_parser("check", help="integrity of a state directory")
    check.add_argument("state_dir", help="the directory organizational state was written to")
    check.set_defaults(handler=_check)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    sys.exit(main())

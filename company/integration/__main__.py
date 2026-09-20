"""CLI: evaluate the production integration gate, read-only.

    python -m company.integration check --repo-root .
    python -m company.integration check --repo-root . --json
    python -m company.integration policy

`check` writes nothing unless `--output-dir` is given, and even then it writes
only the derived report, under the directory the caller named. Nothing in this
command touches production.

The exit code is the verdict: 0 for READY, 1 for BLOCKED, 2 for
INSUFFICIENT_EVIDENCE. A caller that wants the report without the verdict
deciding its own exit status reads the JSON.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from .model import Readiness
from .policy import DEFAULT_POLICY
from .report import build_report, render_text
from .store import ReadinessReportStore
from .suites import SuiteEvidence


_EXIT = {
    Readiness.READY: 0,
    Readiness.BLOCKED: 1,
    Readiness.INSUFFICIENT_EVIDENCE: 2,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m company.integration")
    commands = root.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="evaluate the gate over a checkout")
    check.add_argument("--repo-root", default=".")
    check.add_argument("--as-of", type=dt.date.fromisoformat)
    check.add_argument(
        "--state-dir", help="a company state directory, for the record-backed conditions"
    )
    check.add_argument(
        "--suite-evidence", help="a JSON file of reported test-suite runs"
    )
    check.add_argument(
        "--output-dir", help="write the derived report here (append-only)"
    )
    check.add_argument("--json", action="store_true", help="print canonical JSON")
    check.add_argument("--verbose", action="store_true", help="show passing detail too")

    commands.add_parser("policy", help="print the required/advisory split")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "policy":
        return _policy()
    return _check(args)


def _policy() -> int:
    print(f"gate policy v{DEFAULT_POLICY.version}")
    print(f"\nrequired ({len(DEFAULT_POLICY.required)}) - an unsatisfied one blocks readiness")
    for check_id in sorted(DEFAULT_POLICY.required):
        print(f"  {check_id}")
    print(f"\nadvisory ({len(DEFAULT_POLICY.advisory)}) - visible, never blocking")
    for check_id in sorted(DEFAULT_POLICY.advisory):
        print(f"  {check_id}")
    print(f"\nmay answer not_applicable ({len(DEFAULT_POLICY.not_applicable_allowed)})")
    for check_id in sorted(DEFAULT_POLICY.not_applicable_allowed):
        print(f"  {check_id}")
    return 0


def _check(args: argparse.Namespace) -> int:
    suites = (
        SuiteEvidence.from_path(args.suite_evidence)
        if args.suite_evidence
        else SuiteEvidence()
    )
    report = build_report(
        args.repo_root,
        as_of=args.as_of,
        suites=suites,
        state_dir=args.state_dir,
    )
    if args.json:
        print(report.canonical_json(), end="")
    else:
        print(render_text(report, verbose=args.verbose), end="")
    if args.output_dir:
        store = ReadinessReportStore(args.output_dir)
        path = store.put(report)
        if not args.json:
            print(f"written     {path}")
    return _EXIT[report.readiness]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

"""CLI: evaluate the production integration gate, read-only.

    python -m company.integration check --repo-root .
    python -m company.integration check --repo-root . --json
    python -m company.integration policy
    python -m company.integration required-suites --repo-root . --json

`required-suites` exists so that a caller who must *produce* the evidence can
ask what evidence is wanted, instead of keeping a second copy of the list and
drifting from it. It is the only supported way for the external engineering
runner to learn the set: that package may not import - or even name - the
capsule layer the set is derived from, so the boundary has to be this command
line. It reads the checkout and prints; it runs nothing.

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
from pathlib import Path
import sys

from ai_platform.serde import dumps

from .checks import GateInputs, GateScan, load_capsule_index
from .dependencies import build_dependency_graph
from .model import Readiness
from .policy import DEFAULT_POLICY
from .report import build_report, render_text
from .store import ReadinessReportStore
from .suites import (
    SuiteEvidence,
    SuiteOrigin,
    resolve_required_suites,
    undeclared_company_os_suites,
)


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
    check.add_argument(
        "--changed-path",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "a repository-relative path this change touches; repeatable. Only ever "
            "widens the required-suite set, never narrows it."
        ),
    )
    check.add_argument("--json", action="store_true", help="print canonical JSON")
    check.add_argument("--verbose", action="store_true", help="show passing detail too")

    commands.add_parser("policy", help="print the required/advisory split")

    suites = commands.add_parser(
        "required-suites",
        help="print the suites this checkout requires evidence for",
    )
    suites.add_argument("--repo-root", default=".")
    suites.add_argument("--capsule-root", help="a capsule seed directory, for tests")
    suites.add_argument(
        "--changed-path", action="append", default=[], metavar="PATH", help="repeatable"
    )
    suites.add_argument("--json", action="store_true", help="print canonical JSON")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "policy":
        return _policy()
    if args.command == "required-suites":
        return _required_suites(args)
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
        changed_paths=tuple(args.changed_path),
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


def _required_suites(args: argparse.Namespace) -> int:
    """Print the derived required set. Exit 2 when it could not be resolved.

    The exit code matters: a caller scripting `--suite-evidence` off this
    output must not treat a partial list as the whole answer, and 2 is the
    gate's own code for "evidence is missing", which is exactly the condition.
    """
    inputs = GateInputs(
        repo_root=Path(args.repo_root).resolve(),
        as_of=dt.date.today(),
        capsule_root=Path(args.capsule_root).resolve() if args.capsule_root else None,
    )
    required = resolve_required_suites(
        load_capsule_index(inputs),
        changed_paths=tuple(args.changed_path),
        # The CLI parses the tree for itself rather than leaving the graph out.
        # Omitting it is a supported call - it produces an unresolved set and
        # exit 2 - but it would make this command print a *narrower* list than
        # the gate requires, and a caller scripting `--suite-evidence` off it
        # would then run less than the gate asks for and call the result green.
        graph=build_dependency_graph(GateScan.of(inputs.repo_root)),
    )
    undeclared = undeclared_company_os_suites(inputs.repo_root, required)
    if args.json:
        print(
            dumps(
                {
                    **required.to_dict(),
                    "fingerprint": required.fingerprint(),
                    "undeclared_company_os_suites": list(undeclared),
                }
            ),
            end="",
        )
    else:
        print(f"required suites ({len(required)}) - set {required.fingerprint()}")
        for item in required:
            print(f"  {item.suite}")
            print(f"      {item.reason()}")
        for reason in required.unresolved:
            print(f"  UNRESOLVED: {reason}")
        if undeclared:
            print(
                f"\nnot required ({len(undeclared)}): no capsule declares them and "
                "their imports reach no capsule-owned code:"
            )
            for suite in undeclared:
                print(f"  {suite}")
    return 0 if required.resolved else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

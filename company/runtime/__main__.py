"""Small development CLI for the Company OS runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from company.validation.errors import CompanyOSError

from .config import load_validated_company_config
from .routing import match_capabilities


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m company.runtime")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="directory containing the four Company OS bootstrap YAML files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate bootstrap configuration")
    subparsers.add_parser("employees", help="list employees deterministically")
    match = subparsers.add_parser("match", help="match required capabilities")
    match.add_argument("capabilities", nargs="+", help="required capability names")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_validated_company_config(args.config_dir)
        if args.command == "validate":
            count = len(config.org_registry["employees"])
            print(f"Company OS bootstrap configuration is valid ({count} employees).")
        elif args.command == "employees":
            for employee_id, employee in sorted(config.org_registry["employees"].items()):
                capabilities = ",".join(employee["capabilities"])
                print(
                    f"{employee_id}\t{employee['state']}\t{employee['department']}\t"
                    f"manager={employee['manager']}\tcapabilities={capabilities}"
                )
        elif args.command == "match":
            result = match_capabilities(args.capabilities, config)
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0
    except (CompanyOSError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

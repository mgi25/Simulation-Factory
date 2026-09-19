"""A read-only command line over the workforce model.

Four subcommands, none of which writes anything:

    coverage CAP...   who can do this, actively and organizationally
    spof              capabilities with exactly one organizational provider
    graph [CAP]       the capability model, or one capability's neighbourhood
    integrity         every cross-record invariant, over the shipped registries

`--expand` on `coverage` pulls in what the named capabilities comprise and
require, which is how you find out that a request for `cinematography` is really
a request for four things.

The commands that would change the organization are absent on purpose: there is
no `hire`, no `activate`, no `archive`. A proposal is a record a human reads,
and a CLI verb is exactly the affordance that turns one into an action by
accident.
"""

from __future__ import annotations

import argparse
import sys

from ai_platform.serde import dumps
from company.runtime.config import load_company_config

from .capabilities import CapabilityRegistry, RelationKind
from .coverage import assess_coverage, organization_single_points_of_failure
from .errors import WorkforceError
from .integrity import check_integrity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m company.workforce",
        description="Read-only questions about company capability and coverage.",
    )
    parser.add_argument("--config-dir", default=None, help="directory holding the bootstrap YAML")
    sub = parser.add_subparsers(dest="command", required=True)

    coverage = sub.add_parser("coverage", help="who provides these capabilities")
    coverage.add_argument("capabilities", nargs="+")
    coverage.add_argument(
        "--expand",
        action="store_true",
        help="include what the named capabilities comprise and require",
    )

    sub.add_parser("spof", help="capabilities with a single organizational provider")

    graph = sub.add_parser("graph", help="the capability model, or one neighbourhood")
    graph.add_argument("capability", nargs="?")

    sub.add_parser("integrity", help="cross-record invariants over the shipped registries")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_company_config(args.config_dir)
    registry = CapabilityRegistry.load(config.org_registry)
    try:
        payload = _dispatch(args, registry, config)
    except WorkforceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(dumps(payload), end="")
    return 0


def _dispatch(args: argparse.Namespace, registry: CapabilityRegistry, config) -> object:
    if args.command == "coverage":
        return assess_coverage(args.capabilities, registry, expand=args.expand).to_dict()
    if args.command == "spof":
        return [
            coverage.to_dict() for coverage in organization_single_points_of_failure(registry)
        ]
    if args.command == "graph":
        if args.capability:
            capability = registry.graph.get(args.capability)
            return {
                "capability": capability.capability_id,
                "criticality": capability.criticality.value,
                "comprises": list(
                    registry.graph.descendants(capability.capability_id, RelationKind.COMPRISES)
                ),
                "requires": list(
                    registry.graph.descendants(capability.capability_id, RelationKind.REQUIRES)
                ),
                "adjacent": list(registry.graph.adjacent([capability.capability_id])),
                "providers": registry.providers(capability.capability_id).to_dict(),
            }
        return {
            "capabilities": list(registry.graph.ids()),
            "relations": len(registry.graph.relations),
            "unused": list(registry.unused_capabilities()),
        }
    return list(check_integrity(registry, permissions=config.permissions))


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())

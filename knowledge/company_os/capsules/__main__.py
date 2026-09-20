"""A session's shortest path to its own context, with no Python in between.

    python -m knowledge.company_os.capsules select --path company/runtime/ \
        --capability capability_routing
    python -m knowledge.company_os.capsules show company-runtime
    python -m knowledge.company_os.capsules check

`select` prints references and the cost of sending them. `show` prints one
capsule's canonical JSON, which is the thing you paste. `check` runs the
integrity and staleness sweeps and exits non-zero when either finds something,
so it can be a pre-merge step later without changing shape.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from ai_platform.serde import dumps
from knowledge.company_os.capsules.budget import CapsuleError
from knowledge.company_os.capsules.index import REPO_ROOT, SEED_ROOT, CapsuleIndex
from knowledge.company_os.capsules.select import TaskQuery, select_capsules
from knowledge.company_os.ledger import DEFAULT_ROOT, KnowledgeStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="knowledge.company_os.capsules")
    parser.add_argument("--root", default=str(SEED_ROOT), help="capsule directory")
    sub = parser.add_subparsers(dest="command", required=True)

    select = sub.add_parser("select", help="choose capsules for a task")
    select.add_argument("--path", action="append", default=[], help="a repository path")
    select.add_argument("--capability", action="append", default=[], help="a capability tag")
    select.add_argument("--id", action="append", default=[], help="an explicit capsule id")
    select.add_argument("--owner", default="")
    select.add_argument("--max", type=int, default=6, dest="max_capsules")
    select.add_argument("--no-dependencies", action="store_true")
    select.add_argument("--knowledge", action="store_true", help="also print knowledge refs")

    show = sub.add_parser("show", help="print one capsule as canonical JSON")
    show.add_argument("capsule_id")

    sub.add_parser("list", help="print every capsule id, type and size")
    sub.add_parser("check", help="run the integrity and staleness sweeps")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    index = CapsuleIndex.load(args.root)

    if args.command == "list":
        for capsule in index.all():
            print(f"{capsule.id:28s} {capsule.type.value:8s} {capsule.size_chars():5d} chars")
        print(f"{len(index)} capsules, {index.total_chars()} chars")
        return 0

    if args.command == "show":
        try:
            print(dumps(index.get(args.capsule_id)), end="")
        except CapsuleError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    if args.command == "check":
        problems = index.integrity(KnowledgeStore(DEFAULT_ROOT), REPO_ROOT)
        stale = index.staleness(dt.date.today(), KnowledgeStore(DEFAULT_ROOT))
        for problem in problems:
            print(f"integrity: {problem}")
        for entry in stale:
            for reason in entry.reasons:
                print(f"stale: {entry.capsule_id}: {reason}")
        if not problems and not stale:
            print(f"{len(index)} capsules: integrity clean, none stale")
        return 1 if problems or stale else 0

    selection = select_capsules(
        index,
        TaskQuery(
            paths=tuple(args.path),
            capabilities=tuple(args.capability),
            capsule_ids=tuple(args.id),
            owner=args.owner,
            include_dependencies=not args.no_dependencies,
            max_capsules=args.max_capsules,
        ),
    )
    for ref in selection.refs():
        print(f"{ref.ref}\t{ref.reason}")
    if args.knowledge:
        for ref in selection.knowledge_refs():
            print(f"{ref.ref}\t{ref.reason}")
    metrics = selection.metrics()
    print(
        f"# {metrics.capsules_selected}/{metrics.capsules_considered} capsules, "
        f"{metrics.chars} chars, {metrics.rejected_by_budget} cut by budget",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

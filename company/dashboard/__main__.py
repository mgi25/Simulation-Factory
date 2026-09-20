"""CLI: build and show deterministic Company OS executive views."""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from .brief import build_brief
from .builder import build_snapshot
from .store import DashboardStore


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m company.dashboard")
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build a read-only snapshot and CEO brief")
    build.add_argument("--state-dir", required=True)
    build.add_argument("--output-dir", required=True)
    build.add_argument("--as-of", type=dt.date.fromisoformat)
    show = commands.add_parser("show", help="show a stored snapshot's compact CEO brief")
    show.add_argument("--output-dir", required=True)
    show.add_argument("--snapshot", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "build":
        snapshot = build_snapshot(args.state_dir, as_of=args.as_of)
        brief = build_brief(snapshot)
        store = DashboardStore(args.output_dir)
        path = store.put_snapshot(snapshot)
        brief_path = store.put_brief(brief)
        print(snapshot.snapshot_id)
        print(path)
        print(brief_path)
        return 0
    snapshot = DashboardStore(args.output_dir).get_snapshot(args.snapshot)
    print(build_brief(snapshot).render_text(), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


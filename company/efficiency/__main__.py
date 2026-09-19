from __future__ import annotations

import argparse
from pathlib import Path
import sys

from ai_platform.serde import dumps, to_jsonable

from .benchmark import run_default_benchmarks
from .store import EfficiencyStore
from .telemetry import summarise_efficiency


def main() -> int:
    if sys.argv[1:2] and sys.argv[1] in {"real", "report"}:
        return _real(sys.argv[1:])
    parser = argparse.ArgumentParser(description="Run credit-free Company OS efficiency benchmarks")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = dumps(run_default_benchmarks(args.repo).to_dict())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


def _real(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m company.efficiency real",
        description="Show append-only efficiency records from real executions",
    )
    parser.add_argument("command", choices=("real", "report"))
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--task")
    parser.add_argument("--capability")
    parser.add_argument("--model")
    parser.add_argument(
        "--summary-only", action="store_true", help="omit individual records"
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    records = list(EfficiencyStore(args.state_dir).all_records())
    if args.task:
        records = [record for record in records if record.task_id == args.task]
    if args.capability:
        records = [
            record for record in records
            if args.capability in record.capabilities_selected
        ]
    if args.model:
        records = [record for record in records if record.model == args.model]
    records = records[-args.limit :]
    payload = {
        "summary": to_jsonable(summarise_efficiency(tuple(records))),
        "records": [] if args.summary_only else [record.to_dict() for record in records],
    }
    print(dumps(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
from pathlib import Path

from ai_platform.serde import dumps

from .benchmark import run_default_benchmarks


def main() -> int:
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


if __name__ == "__main__":
    raise SystemExit(main())

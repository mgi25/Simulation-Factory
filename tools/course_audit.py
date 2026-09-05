"""Audit a race course's geometry without running a race.

    python -m tools.course_audit --course machine
    python -m tools.course_audit --course prototype --seed 1234

Exits non-zero if anything is reported as an error, so it can gate a batch.
"""

from __future__ import annotations

import argparse
import sys

from race.audit import audit_course, format_findings
from race.courses import COURSE_NAMES, DEFAULT_COURSE, build_course


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a course's geometry")
    parser.add_argument("--course", choices=COURSE_NAMES, default=DEFAULT_COURSE)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument(
        "--all", action="store_true", help="audit every registered course"
    )
    args = parser.parse_args()

    names = COURSE_NAMES if args.all else (args.course,)
    failed = False
    for name in names:
        course = build_course(name, args.seed)
        findings = audit_course(course)
        print(format_findings(course, findings))
        print()
        failed = failed or any(f.severity == "error" for f in findings)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

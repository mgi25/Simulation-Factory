"""Per-file results from JUnit XML, and SuiteEvidence for the derived required suites.

usage: build_evidence.py --required <required-suites.json> --junit <xml> [--junit <xml> ...]
                         --out <suite-evidence.json> --per-file <per-file.json>
                         --reported-by <id> --observed-on <YYYY-MM-DD> --where <label>
Evidence is only ever built from runs that happened: a required suite with no
test case in the supplied XML is reported missing, never filled in.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ap = argparse.ArgumentParser()
ap.add_argument("--required", required=True)
ap.add_argument("--junit", action="append", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--per-file", required=True)
ap.add_argument("--reported-by", required=True)
ap.add_argument("--observed-on", required=True)
ap.add_argument("--where", required=True)
ap.add_argument("--production-suite", action="append", default=[], help="a production-environment suite (company_os false), as P6B/P6C classified them")
args = ap.parse_args()

required = [r["suite"] for r in json.loads(Path(args.required).read_text(encoding="utf-8"))["requirements"]]
counts: dict[str, dict[str, float]] = defaultdict(lambda: {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "time": 0.0})
failed_ids: list[str] = []
sources: dict[str, str] = {}


def suite_of(classname: str) -> str:
    parts = classname.split(".")
    for i in range(len(parts), 0, -1):
        candidate = "/".join(parts[:i]) + ".py"
        if Path(candidate).name.startswith("test_"):
            return candidate if candidate.startswith("tests/") else "tests/" + candidate
    return classname


for xml in args.junit:
    root = ET.parse(xml).getroot()
    for case in root.iter("testcase"):
        suite = suite_of(case.get("classname", ""))
        sources.setdefault(suite, Path(xml).name)
        row = counts[suite]
        row["time"] += float(case.get("time") or 0)
        node = f"{suite}::{case.get('name')}"
        if case.find("failure") is not None:
            row["failed"] += 1
            failed_ids.append(node)
        elif case.find("error") is not None:
            row["error"] += 1
            failed_ids.append(node + " [error]")
        elif case.find("skipped") is not None:
            row["skipped"] += 1
        else:
            row["passed"] += 1

results, missing = [], []
for suite in sorted(required):
    if suite not in counts:
        missing.append(suite)
        continue
    c = counts[suite]
    bad = int(c["failed"] + c["error"])
    selected = int(c["passed"] + c["failed"] + c["error"] + c["skipped"])
    results.append(
        {
            "company_os": suite not in args.production_suite,
            "failed": bad,
            "note": f"{int(c['passed'])} passed, {bad} failed, {int(c['skipped'])} skipped in {c['time']:.2f}s ({args.where}; junit {sources[suite]})",
            "observed_on": args.observed_on,
            "passed": bad == 0,
            "reported_by": args.reported_by,
            "selected": selected,
            "suite": suite,
        }
    )

Path(args.out).write_text(json.dumps({"max_age_days": 7, "results": results}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
per_file = {s: {k: (round(v, 2) if k == "time" else int(v)) for k, v in c.items()} for s, c in sorted(counts.items())}
Path(args.per_file).write_text(json.dumps({"files": per_file, "failed_ids": sorted(failed_ids)}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
tot = {k: int(sum(c[k] for c in counts.values())) for k in ("passed", "failed", "error", "skipped")}
red = [r["suite"] for r in results if not r["passed"]]
print(json.dumps({"files": len(counts), "totals": tot, "required": len(required), "represented": len(results), "missing": missing, "red_required": red}, indent=1))
sys.exit(1 if missing else 0)

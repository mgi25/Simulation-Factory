"""Check that every generated number in this directory derives from its rows.

    python docs/evidence/company_os_p6c_experience_store/verify_evidence.py [--projects <projects dir>]

- recomputes the replay summary from `replay-results.json`'s own rows with
  `company.experience.replay.summarise` and compares it field by field;
- recomputes the replay fingerprint and checks the repeat run matched it;
- recomputes the counts in `replay-validity-today.json` from its rows;
- with `--projects`, re-digests every historical source directory and checks
  it against `replay-corpus.json` (the inputs are outside git).

Exit 0 when everything matches, 1 otherwise. Prints what it checked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from company.experience.replay import CorpusSource, corpus_manifest, replay_fingerprint, summarise  # noqa: E402


FOCUSED = (
    "tests/test_company_experience_store.py",
    "tests/test_company_experience_retrieval.py",
    "tests/test_company_external_engineering_runner.py",
    "tests/test_engineering_runner_execution_context.py",
    "tests/test_external_engineering_runner.py",
    "tests/test_company_os_capsules.py",
    "tests/test_company_dependency_graph.py",
    "tests/test_company_integration_gate.py",
    "tests/test_company_session_execution.py",
    "tests/test_company_engineering_execution.py",
    "tests/test_company_read_authority.py",
    "tests/test_company_efficiency.py",
)
BRANCH_GUARD = "::test_this_branch_changed_no_race_fight_or_v30_code"


def _lines(name: str) -> set[str]:
    return {line.strip() for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line.strip()}


def _gate(name: str) -> dict:
    report = json.loads((HERE / name).read_text(encoding="utf-8"))
    checks = [c for section in report["sections"] for c in section["checks"]]
    required = set(report["required_check_ids"])
    counts: dict[str, dict[str, int]] = {"required": {}, "advisory": {}}
    for check in checks:
        side = "required" if check["check_id"] in required else "advisory"
        counts[side][check["status"]] = counts[side].get(check["status"], 0) + 1
    failing = sorted(c["check_id"] for c in checks if c["check_id"] in required and c["status"] != "pass")
    return {
        "report_id": report["report_id"],
        "source_commit": report["source"]["source_commit"],
        "counts": counts,
        "failing_required": failing,
        "blockers": len(report["blockers"]),
        "readiness": "READY" if not failing else ("BLOCKED" if any(c["status"] == "fail" for c in checks if c["check_id"] in required) else "INSUFFICIENT_EVIDENCE"),
    }


def validation_summary() -> dict:
    """Every validation headline, derived from the archived files alone."""
    failures = _lines("full-suite-failures-16d5a39.txt")
    baseline = _lines("baseline-failures-main.txt")
    guards = {f for f in failures if f.endswith(BRANCH_GUARD)}
    extra = sorted(failures - baseline - guards)
    rerun = {r["suite"]: r for r in json.loads((HERE / "runner-suite-rerun-16d5a39.json").read_text(encoding="utf-8"))["results"]}
    per_file = {r["suite"]: r for r in json.loads((HERE / "full-suite-per-file-16d5a39.json").read_text(encoding="utf-8"))["results"]}
    focused = {}
    for suite in FOCUSED:
        row = rerun.get(suite) or per_file.get(suite)
        focused[suite] = {"selected": row["selected"], "failed": row["failed"], "source": "whole-suite re-run" if suite in rerun else "chunked run"}
    required = json.loads((HERE / "required-suites.json").read_text(encoding="utf-8"))
    selected = sum(r["selected"] for r in per_file.values())
    failed = sum(r["failed"] for r in per_file.values())
    return {
        "full_suite_16d5a39": {
            "suites": len(per_file),
            "selected": selected,
            "failed": failed,
            "failures": len(failures),
            "baseline_failures_present": len(baseline & failures),
            "baseline_failures_absent": sorted(baseline - failures),
            "branch_scope_guards": sorted(guards),
            "outside_baseline_and_guards": extra,
            "outside_resolved_by_whole_suite_rerun": [
                f for f in extra if rerun.get(f.split("::", 1)[0], {}).get("failed") == 0
            ],
        },
        "focused": focused,
        "required_suites": {
            "count": len(required["requirements"]),
            "fingerprint": required["fingerprint"],
            "unresolved": required["unresolved"],
            "undeclared_company_os_suites": len(required["undeclared_company_os_suites"]),
        },
        "gate_on_branch": _gate("gate-report-branch.json"),
        "gate_post_merge_modelled": _gate("gate-report-post-merge-modelled.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", type=Path, default=None)
    parser.add_argument("--write", action="store_true", help="write validation-summary.json from the archived files")
    args = parser.parse_args()
    problems: list[str] = []
    report = json.loads((HERE / "replay-results.json").read_text(encoding="utf-8"))
    derived = summarise(report["rows"])
    for key in sorted(set(derived) | set(report["summary"])):
        if derived.get(key) != report["summary"].get(key):
            problems.append(f"summary.{key}: stored {report['summary'].get(key)!r}, rows give {derived.get(key)!r}")
    if replay_fingerprint(report) != report.get("replay_fingerprint"):
        problems.append("replay_fingerprint does not recompute")
    if report.get("replay_fingerprint") != report.get("repeat_fingerprint"):
        problems.append("the repeat run produced a different replay fingerprint")
    today = json.loads((HERE / "replay-validity-today.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for row in today["episodes"]:
        counts[row["validity"]] = counts.get(row["validity"], 0) + 1
    if counts != today["counts"]:
        problems.append(f"validity-today counts {today['counts']} do not match rows {counts}")
    if len(today["episodes"]) != len(report["episodes"]):
        problems.append("validity-today does not cover every captured episode")
    if args.projects is not None:
        sys.path.insert(0, str(HERE))
        from replay_harness import REPO as HARNESS_REPO, SOURCES  # noqa: E402

        corpus = json.loads((HERE / "replay-corpus.json").read_text(encoding="utf-8"))["sources"]
        stored = {c["label"]: c for c in corpus}
        for label, where in SOURCES:
            source = HARNESS_REPO / where[len("@repo/"):] if where.startswith("@repo/") else args.projects / where
            if label not in stored:
                continue
            [fresh] = corpus_manifest([CorpusSource(label, source)])
            if fresh["sha256"] != stored[label]["sha256"]:
                problems.append(f"source {label} has changed since the replay ({fresh['record_files']} files now)")
    derived_validation = validation_summary()
    target = HERE / "validation-summary.json"
    if args.write:
        target.write_text(json.dumps(derived_validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif not target.is_file() or json.loads(target.read_text(encoding="utf-8")) != derived_validation:
        problems.append("validation-summary.json does not match what the archived files derive")
    checked = ["summary from rows", "replay fingerprint", "repeat fingerprint", "validity-today counts", "validation summary"]
    if args.projects is not None:
        checked.append("source digests")
    print(json.dumps({"checked": checked, "problems": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

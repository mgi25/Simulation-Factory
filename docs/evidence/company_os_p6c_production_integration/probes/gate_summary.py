"""Summarise a gate report JSON: counts, failing required checks, blockers, readiness."""

import json
import sys
from collections import Counter

r = json.load(open(sys.argv[1], encoding="utf-8"))
checks = [c for s in r["sections"] for c in s["checks"]]
req = set(r["required_check_ids"])
failing = sorted(c["check_id"] for c in checks if c["check_id"] in req and c["status"] != "pass")
hard_fail = any(c["status"] == "fail" for c in checks if c["check_id"] in req)
readiness = "READY" if not failing else ("BLOCKED" if hard_fail else "INSUFFICIENT_EVIDENCE")
out = {
    "report_id": r["report_id"],
    "source_commit": r["source"].get("source_commit"),
    "authorizes_production_integration": r.get("authorizes_production_integration"),
    "policy_version": r.get("policy_version"),
    "required": dict(Counter(c["status"] for c in checks if c["check_id"] in req)),
    "advisory": dict(Counter(c["status"] for c in checks if c["check_id"] not in req)),
    "failing_required": failing,
    "blockers": [(b["check_id"], b["evidence"]) for b in r["blockers"]],
    "advisory_not_pass": sorted(c["check_id"] for c in checks if c["check_id"] not in req and c["status"] != "pass"),
    "readiness": readiness,
}
print(json.dumps(out, indent=1))

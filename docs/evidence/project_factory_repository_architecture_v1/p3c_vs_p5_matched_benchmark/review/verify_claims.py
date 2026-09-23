"""Independent deterministic re-verification of the benchmark's headline numbers.

This does NOT reuse collect_arm.py. It walks the raw runner state directories
itself, sums every session it finds, recomputes the pooled statistics and the
range-overlap verdicts, and then checks those against the literal numbers
asserted in RESULT.md.

It verifies arithmetic and accounting completeness. It cannot verify judgement,
so it is not a substitute for the independent reviewer.
"""

import json
import pathlib
import re
import sys

P = pathlib.Path(r"C:\Users\mgial\OneDrive\Documents\projects")
STATE = P / "project-factory-runner-state"

ARMS = {
    "control1": "p3c-vs-p5-control",
    "challenger1": "p3c-vs-p5-challenger",   # the void attempt
    "challenger2": "p3c-vs-p5-challenger2",
    "control2": "p3c-vs-p5-control2",
    "challenger3": "p3c-vs-p5-challenger3",
}
MATCHED_CONTROL = ["control1", "control2"]
MATCHED_CHALLENGER = ["challenger2", "challenger3"]

FIELDS = ["turns", "input_units", "cache_read_units", "cache_creation_units",
          "output_units", "cost_usd", "duration_s"]

failures = []
notes = []


def check(label, got, want, tol=0.0):
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: recomputed {got}  claimed {want}")
    if not ok:
        failures.append(f"{label}: recomputed {got} but RESULT.md claims {want}")
    return ok


def scan_arm(slot):
    """Sum every session file found anywhere under this arm's runner dir."""
    root = STATE / ARMS[slot]
    totals = {f: 0 for f in FIELDS}
    totals["paid_sessions"] = 0
    by_role = {}
    models = {}
    session_ids = set()
    for sfile in root.rglob("sessions.json"):
        payload = json.loads(sfile.read_text(encoding="utf-8"))
        declared = payload.get("paid_session_count")
        listed = payload.get("sessions", [])
        if declared is not None and declared != len(listed):
            failures.append(
                f"{slot} {sfile.parent.name}: declared {declared} paid sessions "
                f"but listed {len(listed)}")
        for s in listed:
            sid = s.get("session_id")
            if sid in session_ids:
                failures.append(f"{slot}: session {sid} counted twice")
            session_ids.add(sid)
            role = s.get("role", "?")
            totals["paid_sessions"] += 1
            by_role.setdefault(role, {f: 0 for f in FIELDS} | {"paid_sessions": 0})
            by_role[role]["paid_sessions"] += 1
            models.setdefault(role, set()).add(s.get("model"))
            for f in FIELDS:
                v = s.get(f)
                if not isinstance(v, (int, float)):
                    failures.append(f"{slot} {role}: field {f} is {v!r}, not a number")
                    continue
                totals[f] += v
                by_role[role][f] += v
    return totals, by_role, models, session_ids


print("=" * 78)
print("INDEPENDENT RE-VERIFICATION (recomputed from raw runner state)")
print("=" * 78)

arm_totals, arm_roles, arm_models, all_ids = {}, {}, {}, set()
for slot in ARMS:
    t, r, m, ids = scan_arm(slot)
    arm_totals[slot], arm_roles[slot], arm_models[slot] = t, r, m
    overlap = all_ids & ids
    if overlap:
        failures.append(f"{slot} shares session ids with another arm: {overlap}")
    all_ids |= ids
    print(f"\n{slot}: sessions={t['paid_sessions']} turns={t['turns']} "
          f"cache_read={t['cache_read_units']} cost=${t['cost_usd']:.8f}")
    for role in sorted(r):
        print(f"    {role}: model={sorted(x for x in m[role] if x)} "
              f"turns={r[role]['turns']} cost=${r[role]['cost_usd']:.8f}")

print(f"\nDistinct provider sessions across every arm: {len(all_ids)}")
print("Every session id is unique:", len(all_ids) == sum(
    arm_totals[s]["paid_sessions"] for s in ARMS))

# --- pooled, recomputed independently -----------------------------------
print("\n" + "=" * 78)
print("POOLED (matched pairs only; void attempt excluded by design)")
print("=" * 78)

pooled = {}
for f in FIELDS + ["paid_sessions"]:
    cv = [arm_totals[s][f] for s in MATCHED_CONTROL]
    gv = [arm_totals[s][f] for s in MATCHED_CHALLENGER]
    cm, gm = sum(cv) / len(cv), sum(gv) / len(gv)
    overlap = not (max(gv) < min(cv) or min(gv) > max(cv))
    pooled[f] = {"cm": cm, "gm": gm,
                 "pct": (100.0 * (gm - cm) / cm) if cm else None,
                 "overlap": overlap}
    print(f"{f:<24} control {cm:>14.4f}  challenger {gm:>14.4f}  "
          f"{pooled[f]['pct']:>+8.2f}%  overlap={overlap}")

dev_c = [arm_roles[s]["developer"]["cost_usd"] for s in MATCHED_CONTROL]
dev_g = [arm_roles[s]["developer"]["cost_usd"] for s in MATCHED_CHALLENGER]
rev_c = [arm_roles[s]["reviewer"]["cost_usd"] for s in MATCHED_CONTROL]
rev_g = [arm_roles[s]["reviewer"]["cost_usd"] for s in MATCHED_CHALLENGER]

print("\n" + "=" * 78)
print("CROSS-CHECK AGAINST RESULT.md CLAIMS")
print("=" * 78)

md = (P / "wt-bench-evidence" / "docs" / "evidence"
      / "project_factory_repository_architecture_v1"
      / "p3c_vs_p5_matched_benchmark" / "RESULT.md").read_text(encoding="utf-8")

print("\nHeadline cost claim:")
check("whole-task cost change %", round(pooled["cost_usd"]["pct"], 2), -46.47, 0.01)
check("control mean cost", round(pooled["cost_usd"]["cm"], 4), 0.8723, 0.0001)
check("challenger mean cost", round(pooled["cost_usd"]["gm"], 4), 0.4670, 0.0001)
check("cost ranges do NOT overlap", pooled["cost_usd"]["overlap"], False)

print("\nStage split:")
check("developer mean cost change %",
      round(100 * (sum(dev_g) / 2 - sum(dev_c) / 2) / (sum(dev_c) / 2), 2), -69.33, 0.01)
check("reviewer mean cost change %",
      round(100 * (sum(rev_g) / 2 - sum(rev_c) / 2) / (sum(rev_c) / 2), 2), 9.11, 0.01)
check("developer ranges do NOT overlap",
      not (max(dev_g) < min(dev_c) or min(dev_g) > max(dev_c)), False)
check("reviewer ranges DO overlap",
      not (max(rev_g) < min(rev_c) or min(rev_g) > max(rev_c)), True)

print("\nToken dimensions RESULT.md calls NOT ESTABLISHED:")
for f, claimed_pct in (("turns", 50.94), ("cache_read_units", 82.15),
                       ("cache_creation_units", 12.73), ("output_units", 25.97),
                       ("duration_s", 60.93)):
    check(f"{f} change %", round(pooled[f]["pct"], 2), claimed_pct, 0.01)
    check(f"{f} ranges DO overlap", pooled[f]["overlap"], True)

print("\nPer-pair cost claims:")
for i, (c, g, want) in enumerate(
        [("control1", "challenger2", -9.12), ("control2", "challenger3", -71.30)], 1):
    got = 100 * (arm_totals[g]["cost_usd"] - arm_totals[c]["cost_usd"]) / arm_totals[c]["cost_usd"]
    check(f"pair{i} cost change %", round(got, 2), want, 0.01)

print("\nVoid attempt and as-spent:")
check("void attempt cost", round(arm_totals["challenger1"]["cost_usd"], 5), 0.80952, 0.00001)
check("void attempt turns", arm_totals["challenger1"]["turns"], 61)
p5_spent = sum(arm_totals[s]["cost_usd"] for s in MATCHED_CHALLENGER + ["challenger1"])
p3c_spent = sum(arm_totals[s]["cost_usd"] for s in MATCHED_CONTROL)
check("P5 as-spent total", round(p5_spent, 5), 1.74350, 0.00001)
check("P3C as-spent total", round(p3c_spent, 5), 1.74468, 0.00001)
check("as-spent per-result change %",
      round(100 * (p5_spent / 2 - p3c_spent / 2) / (p3c_spent / 2), 2), -0.07, 0.01)

print("\nModel routing:")
for s in MATCHED_CHALLENGER + ["challenger1"]:
    dev = sorted(x for x in arm_models[s].get("developer", set()) if x)
    rev = sorted(x for x in arm_models[s].get("reviewer", set()) if x)
    ok = dev == ["haiku"] and rev == ["sonnet"]
    print(f"  [{'OK ' if ok else 'FAIL'}] {s}: developer={dev} reviewer={rev}")
    if not ok:
        failures.append(f"{s}: expected developer haiku / reviewer sonnet, got {dev}/{rev}")
for s in MATCHED_CONTROL:
    dev = sorted(x for x in arm_models[s].get("developer", set()) if x)
    rev = sorted(x for x in arm_models[s].get("reviewer", set()) if x)
    ok = dev == ["sonnet"] and rev == ["sonnet"]
    print(f"  [{'OK ' if ok else 'FAIL'}] {s}: developer={dev} reviewer={rev}")
    if not ok:
        failures.append(f"{s}: expected sonnet/sonnet, got {dev}/{rev}")

print("\nRESULT.md internal consistency:")
for needed in ("P5_WIN", "46.47", "0.80952", "not established", "UNAVAILABLE",
               "not concealed", "eng-token-efficiency-v4-p5-challenger"):
    present = needed.lower() in md.lower()
    print(f"  [{'OK ' if present else 'FAIL'}] RESULT.md mentions {needed!r}")
    if not present:
        failures.append(f"RESULT.md is missing required text {needed!r}")

print("\n" + "=" * 78)
if failures:
    print(f"VERIFICATION FAILED with {len(failures)} discrepancies:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("VERIFICATION PASSED: every headline number in RESULT.md is reproducible")
print("from raw runner state, every paid session is accounted for exactly once,")
print("and no session id is double counted.")
print("=" * 78)

"""Phase 13: exercise capture/suggest on real history and prove KnowledgeStore untouched.

usage: knowledge_separation.py <worktree> <projects dir> <scratch dir> <out json>
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

WT, PROJECTS, SCRATCH, OUT = (Path(a) for a in sys.argv[1:5])
PY = sys.executable
SOURCES = {
    "repository-architecture": PROJECTS / "project-factory-company-state" / "repository-architecture-v1",
    "repo-exploration-v2": PROJECTS / "project-archives" / "company-os-runner-evidence" / "company-os-repo-exploration-v2-state",
}
KNOWLEDGE_KINDS = ("Fact", "Hypothesis", "Decision", "ExperimentLearning", "FailureLearning")


def digest(root: Path, skip_prefix: str | None = None) -> dict[str, str]:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if skip_prefix and rel.startswith(skip_prefix):
                continue
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def cli(*args: str) -> dict:
    result = subprocess.run([PY, "-m", "company.experience", *args], cwd=WT, capture_output=True, text=True, encoding="utf-8")
    try:
        body = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        body = None
    return {"exit": result.returncode, "json": body, "stderr": result.stderr.strip()[-400:]}


report: dict = {"knowledge_tree_files": None, "sources": {}}
knowledge_before = digest(WT / "knowledge")
report["knowledge_tree_files"] = len(knowledge_before)
source_before = {label: digest(path) for label, path in SOURCES.items()}

for label, source in SOURCES.items():
    copy = SCRATCH / label
    if copy.exists():
        shutil.rmtree(copy)
    shutil.copytree(source, copy)
    state_before = digest(copy, skip_prefix="experience/")
    orders = sorted(json.loads(sorted(p.glob("*.json"))[0].read_text(encoding="utf-8"))["work_order_id"] for p in (copy / "engineering" / "work_orders").iterdir() if p.is_dir())
    capture = cli("capture", "--state-dir", str(copy), "--repo-root", str(WT), "--on", "2026-09-25")
    suggestions = {}
    for order in orders:
        s = cli("suggest", "--state-dir", str(copy), "--repo-root", str(WT), "--work-order", order, "--on", "2026-09-25", "--json")
        body = s["json"] or {}
        suggestions[order] = {
            "exit": s["exit"],
            "status": body.get("status"),
            "abstention": (body.get("abstention") or {}).get("code") if isinstance(body.get("abstention"), dict) else body.get("abstention"),
            "precedents": len(body.get("precedents") or []),
            "advisory_only": body.get("advisory_only"),
            "stderr": s["stderr"] if s["exit"] else "",
        }
    listing = cli("list", "--state-dir", str(copy))
    experience_before_recapture = digest(copy / "experience")
    recapture = cli("capture", "--state-dir", str(copy), "--repo-root", str(WT), "--on", "2026-09-25")
    experience_after_recapture = digest(copy / "experience")
    state_after = digest(copy, skip_prefix="experience/")
    experience_files = sorted(p.relative_to(copy).as_posix() for p in (copy / "experience").rglob("*") if p.is_file()) if (copy / "experience").exists() else []
    kinds = set()
    for rel in experience_files:
        if rel.endswith(".json"):
            try:
                data = json.loads((copy / rel).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(data, dict):
                for key in ("kind", "record_type", "type"):
                    if key in data:
                        kinds.add(f"{key}={data[key]}")
    knowledge_kind_hits = sorted(k for k in kinds if any(k.endswith("=" + name) for name in KNOWLEDGE_KINDS))
    report["sources"][label] = {
        "work_orders": len(orders),
        "capture_exit": capture["exit"],
        "capture_counts": (capture["json"] or {}).get("counts"),
        "suggest_exits": sorted({v["exit"] for v in suggestions.values()}),
        "suggest_status": {k: [v["status"], v["abstention"], v["precedents"]] for k, v in suggestions.items()},
        "all_advisory_only": all(v["advisory_only"] is True for v in suggestions.values() if v["exit"] == 0),
        "episodes_listed": len(((listing["json"] or {}).get("episodes")) or []),
        "recapture_counts": (recapture["json"] or {}).get("counts"),
        "recapture_byte_identical": experience_after_recapture == experience_before_recapture,
        "episode_top_level_keys": sorted(json.loads(next((copy / "experience").rglob("*.json")).read_text(encoding="utf-8"))) if experience_files else [],
        "non_experience_state_identical": state_after == state_before,
        "non_experience_state_files": len(state_before),
        "experience_files_written": len(experience_files),
        "experience_record_kinds": sorted(kinds),
        "knowledge_record_kinds_in_experience": knowledge_kind_hits,
    }

knowledge_after = digest(WT / "knowledge")
report["knowledge_tree_identical"] = knowledge_after == knowledge_before
report["knowledge_records_files"] = sum(1 for k in knowledge_before if k.startswith("company_os/records/"))
report["source_dirs_untouched"] = {label: digest(path) == source_before[label] for label, path in SOURCES.items()}
OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
for label, row in report["sources"].items():
    print(label, {k: v for k, v in row.items() if k != "suggest_status"})

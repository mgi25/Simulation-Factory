"""Regenerate the P6C offline replay from genuine engineering history.

    python docs/evidence/company_os_p6c_experience_store/replay_harness.py \
        --projects C:/Users/mgial/OneDrive/Documents/projects \
        --scratch  <an empty scratch directory> \
        --out      docs/evidence/company_os_p6c_experience_store

Why this is a script beside the evidence and not a Company OS command: it
materialises each historical base commit with `git archive`, and Company OS
holds no process authority (`production.no_publishing_capability`). Everything
that decides anything is `company.experience` - this file only supplies the
inputs: a snapshot copy of each historical state directory (so the replay can
never write into, or be disturbed by, a live one) and a `RepositoryView` of the
repository as it stood at each base commit.

Outputs, all generated, none hand-edited:

    replay-corpus.json     the sources, their record counts and a digest of every record file
    replay-results.json    the full replay report (rows, capture counts, summary)
    replay-validity-today.json  every captured episode judged against today's checkout
    replay-summary.md      tables rendered from the JSON above
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from company.experience import ExperienceStore, RepositoryView, evaluate_validity  # noqa: E402
from company.experience.capture import verify_pointers  # noqa: E402
from company.experience.replay import CorpusSource, corpus_manifest, replay_fingerprint, run_replay  # noqa: E402
from company.integration.checks import GateScan  # noqa: E402
from company.integration.dependencies import build_dependency_graph  # noqa: E402


def canonical_graph(root: Path):
    """P6B's graph, supplied from outside Company OS - the experience package
    never imports the gate that owns it."""
    return build_dependency_graph(GateScan.of(root))


# Every control-plane state directory with engineering history that exists on
# this machine, by label. Found by walking `projects/` for `engineering/
# work_orders`; copies of the one in-git record inside other worktrees are
# left out because they are the same record.
SOURCES: tuple[tuple[str, str], ...] = (
    ("in-git-validation-record", "@repo/docs/validation/company_os_engineering_execution/records"),
    ("aiv2-after", "project-archives/company-os-runner-evidence/company-os-aiv2-after-state"),
    ("consumer", "project-archives/company-os-runner-evidence/company-os-consumer-state"),
    ("repo-exploration-v2", "project-archives/company-os-runner-evidence/company-os-repo-exploration-v2-state"),
    ("repoexpl", "project-archives/company-os-runner-evidence/company-os-repoexpl-state"),
    ("second-dogfood", "project-archives/company-os-runner-evidence/company-os-second-dogfood-state"),
    ("v3b", "project-archives/company-os-runner-evidence/company-os-v3b-runner-state"),
    ("discovery-pilot", "project-archives/company-os-runner-evidence/wt-discovery-pilot-state"),
    ("e2e-pilot", "project-archives/company-os-runner-evidence/wt-e2e-pilot-state"),
    ("e2e-pilot-2", "project-archives/company-os-runner-evidence/wt-e2e-pilot-state2"),
    ("e2e-pilot-3", "project-archives/company-os-runner-evidence/wt-e2e-pilot-state3"),
    ("review-separation", "project-archives/company-os-runner-evidence/wt-rs-state"),
    ("p5-evidence-reviewability", "project-archives/p5-evidence-reviewability-v1/company-state"),
    ("p5-evidence-reviewability-closed", "project-archives/p5-evidence-reviewability-v1/company-state-closed"),
    ("p5-read-authority", "project-archives/p5-read-authority-v1/company-state"),
    ("p3c-vs-p5-control", "project-factory-company-state/p3c-vs-p5-control"),
    ("p3c-vs-p5-control-b", "project-factory-company-state/p3c-vs-p5-control2"),
    ("p3c-vs-p5-challenger", "project-factory-company-state/p3c-vs-p5-challenger"),
    ("p3c-vs-p5-challenger-b", "project-factory-company-state/p3c-vs-p5-challenger2"),
    ("p3c-vs-p5-challenger-c", "project-factory-company-state/p3c-vs-p5-challenger3"),
    ("repository-architecture", "project-factory-company-state/repository-architecture-v1"),
)

# What a historical view needs: the capsule store and every tree P6B's scan
# reads for Company OS questions.
TREE_PATHS = ("company", "ai_platform", "knowledge", "intelligence", "tests", "tools")
CAPTURED_ON = dt.date(2026, 9, 25)


def snapshot(projects: Path, scratch: Path) -> list[CorpusSource]:
    corpus = scratch / "corpus"
    out = []
    for label, where in SOURCES:
        source = REPO / where[len("@repo/"):] if where.startswith("@repo/") else projects / where
        if not (source / "engineering" / "work_orders").is_dir():
            continue
        target = corpus / label
        for sub in ("engineering", "execution", "resource_usage"):
            if (source / sub).is_dir():
                shutil.copytree(source / sub, target / sub)
        out.append(CorpusSource(label, target))
    return out


class Trees:
    """One RepositoryView per historical commit, materialised once."""

    def __init__(self, scratch: Path) -> None:
        self.root = scratch / "trees"
        self.views: dict[str, RepositoryView | None] = {}
        self.errors: dict[str, str] = {}

    def __call__(self, commit: str) -> RepositoryView | None:
        if not commit:
            return None
        if commit not in self.views:
            self.views[commit] = self._build(commit)
        return self.views[commit]

    def _build(self, commit: str) -> RepositoryView | None:
        target = self.root / commit[:12]
        try:
            archive = subprocess.run(
                ["git", "archive", "--format=tar", commit, *TREE_PATHS],
                cwd=REPO, capture_output=True, check=True,
            ).stdout
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(target, filter="data")
        except (subprocess.CalledProcessError, tarfile.TarError, OSError) as exc:
            self.errors[commit] = f"{type(exc).__name__}: {exc}"
            return None
        view = RepositoryView.load(target, graph_builder=canonical_graph)
        # Built here, outside the replay's latency measurement: the graph is a
        # per-commit cost, not a per-query one.
        if view.graph is None:
            self.errors[commit] = f"graph: {view.graph_error}"
        if view.capsules is None:
            self.errors[commit] = f"capsules: {view.capsule_error}"
        return view


def validity_today(report: dict, sources: list[CorpusSource], scratch_store: ExperienceStore) -> dict:
    """Every captured episode judged against the checkout this script runs in."""
    today = RepositoryView.load(REPO)
    by_label = {s.label: s.state_dir for s in sources}
    rows = []
    for episode in scratch_store.episodes():
        problems = verify_pointers(episode, by_label[episode.source])
        verdict = evaluate_validity(episode, today, pointer_problems=problems)
        rows.append(
            {
                "work_order_id": episode.work_order_id,
                "attempt": episode.packet_attempt,
                "source": episode.source,
                "class": episode.engineering_class().value,
                "validity": verdict.status.value,
                "reasons": list(verdict.reasons[:6]),
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["validity"]] = counts.get(row["validity"], 0) + 1
    return {"judged_against": "the checkout running this script", "counts": dict(sorted(counts.items())), "episodes": rows}


def render(report: dict, today: dict, corpus: list[dict], repeat_ok: bool, tree_errors: dict) -> str:
    s = report["summary"]
    lines = [
        "# P6C offline replay - generated, do not edit",
        "",
        "Rendered by `replay_harness.py` from `replay-results.json`, "
        "`replay-validity-today.json` and `replay-corpus.json`.",
        "",
        f"- sources: {len(corpus)} state directories, "
        f"{sum(c['record_files'] for c in corpus)} record files, "
        f"{sum(c['record_bytes'] for c in corpus)} bytes",
        f"- capture: `{json.dumps(report['capture'], sort_keys=True)}`",
        f"- episodes captured: {len(report['episodes'])}",
        f"- repeat run produced the same replay fingerprint: **{repeat_ok}**",
        f"- historical trees that could not be materialised or read: {len(tree_errors)}",
        "",
        "## Leave-future-out replay",
        "",
        "| measure | value |",
        "|---|---|",
    ]
    for key, value in s.items():
        lines.append(f"| {key} | {json.dumps(value, sort_keys=True) if isinstance(value, dict) else value} |")
    lines += ["", "## Per decision", "", "| decided | work order | attempt | eligible | status | top-1 | warnings | changed later | actual |", "|---|---|---|---|---|---|---|---|---|"]
    for row in report["rows"]:
        lines.append(
            "| {decided} | {wo} | {att} | {elig} | {status} | {top} | {warn} | {hit} | {actual} |".format(
                decided=row.get("decided_on", ""),
                wo=row.get("work_order_id", ""),
                att=row.get("attempt", ""),
                elig=row.get("eligible_history", ""),
                status=row.get("status", "") + (f" ({row['abstention']})" if row.get("abstention") else ""),
                top=row.get("top1", ""),
                warn=", ".join(row.get("warnings", ())),
                hit=", ".join(row.get("suggested_files_changed_later", ())),
                actual=row.get("actual_class", ""),
            )
        )
    lines += ["", "## Every captured episode, judged against today's checkout", "", f"counts: `{json.dumps(today['counts'])}`", ""]
    lines += ["| work order | attempt | class | validity | first reason |", "|---|---|---|---|---|"]
    for row in today["episodes"]:
        lines.append(
            f"| {row['work_order_id']} | {row['attempt']} | {row['class']} | {row['validity']} | {(row['reasons'] or [''])[0]} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    if scratch.exists() and any(scratch.iterdir()):
        raise SystemExit(f"--scratch {scratch} must be empty")
    sources = snapshot(args.projects.resolve(), scratch)
    corpus = corpus_manifest(sources)
    trees = Trees(scratch)
    first_store = ExperienceStore(scratch / "store-1")
    report = run_replay(sources, view_for=trees, scratch_store=first_store, captured_on=CAPTURED_ON)
    again = run_replay(sources, view_for=trees, scratch_store=ExperienceStore(scratch / "store-2"), captured_on=CAPTURED_ON)
    repeat_ok = replay_fingerprint(report) == replay_fingerprint(again)
    report["replay_fingerprint"] = replay_fingerprint(report)
    report["repeat_fingerprint"] = replay_fingerprint(again)
    report["tree_errors"] = dict(sorted(trees.errors.items()))
    today = validity_today(report, sources, first_store)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "replay-corpus.json").write_text(json.dumps({"sources": corpus}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "replay-results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "replay-validity-today.json").write_text(json.dumps(today, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "replay-summary.md").write_text(render(report, today, corpus, repeat_ok, trees.errors), encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "capture": report["capture"], "repeat_ok": repeat_ok, "today": today["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

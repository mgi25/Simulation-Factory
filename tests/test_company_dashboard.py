"""Focused proofs for the deterministic, read-only CEO company-state view."""

from __future__ import annotations

import ast
from dataclasses import fields
import datetime as dt
from pathlib import Path

import pytest

from ai_platform.resource_classes import ReasoningClass
from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.usage import Outcome, ResourceUsageRecord
from company.dashboard import (
    AttentionItem, AttentionLevel, Availability, CEODecisionItem,
    CompanyStatePaths, CompanyStateSnapshot, DashboardStore, ExecutiveDimension,
    ExecutiveSection, FreshnessState, SourceReference, SourceSubsystem, build_brief,
    build_snapshot, check_integrity, diff_snapshots,
)
from company.dashboard.models import DashboardError
from company.dashboard.builder import _dependency_cycles
from company.finance import (
    CostCategory, CostRecord, FinanceStore, Money, Recurrence, RevenueCategory,
    RevenueRecord, SpendProposal, SubjectKind, SubjectRef,
)
from company.runtime.config import load_company_config
from company.runtime import (ContextRequirements, ExecutionStore, TaskSpecification,
                             build_session_packet, plan_task)
from company.runtime.usage_store import ResourceUsageStore
from intelligence.research import (
    BatchBudget, ResearchStore, StopCondition, StopReason, open_batch, stop_batch,
)
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.records import Alternative, Evidence


ROOT = Path(__file__).resolve().parents[1]
TODAY = dt.date(2026, 9, 17)


def _sources(tmp_path: Path) -> CompanyStatePaths:
    return CompanyStatePaths.from_root(tmp_path / "company-state")


def _snapshot(tmp_path: Path, **kwargs) -> CompanyStateSnapshot:
    return build_snapshot(sources=_sources(tmp_path), as_of=TODAY, repo_root=ROOT, **kwargs)


def _evidence(kind: str = "invoice", ref: str = "docs/evidence/item.pdf") -> Evidence:
    return Evidence(kind=kind, ref=ref, note="checkable source")


def _cost() -> CostRecord:
    return CostRecord("cost.001", TODAY, Money("12.50", "EUR"), CostCategory.RENDER,
                      SubjectRef(SubjectKind.VIDEO, "video-1"), "invoice-1", (_evidence(),),
                      "finance-owner", TODAY)


def _revenue() -> RevenueRecord:
    return RevenueRecord("rev.001", TODAY, Money("30.00", "EUR"),
                         RevenueCategory.YOUTUBE_AD_REVENUE,
                         SubjectRef(SubjectKind.VIDEO, "video-1"), "studio-export",
                         (_evidence("analytics_export", "exports/studio.csv"),),
                         "finance-owner", TODAY)


def _proposal() -> SpendProposal:
    config = load_company_config(ROOT / "company")
    proposal = SpendProposal(
        proposal_id="spend.001", service="research_api",
        purpose="Measure a recurring research API before adopting it.",
        category=CostCategory.API, recurrence=Recurrence.RECURRING,
        estimated_amount=Money("40.00", "EUR"), period="monthly",
        expected_benefit="Reduce manual screening time with measured coverage.",
        break_even_condition="Two reviewed batches per month.",
        kill_condition="Fewer than two batches for two months.",
        evidence=(_evidence("document", "docs/research/api.md"),),
        proposed_by="research-owner", proposed_on=TODAY,
        alternatives=(Alternative("Keep manual review", "It consumes more measured time."),),
    )
    return proposal.with_reservation(permissions=config.permissions)


def test_empty_company_state_is_deterministic_and_missing_is_not_zero(tmp_path):
    first = _snapshot(tmp_path)
    second = _snapshot(tmp_path)
    assert first == second
    assert first.canonical_json() == second.canonical_json()
    finance = first.section("finance")
    assert finance.availability is Availability.MISSING
    assert "unknown" in finance.missing[0]
    assert "0" not in finance.summary
    assert "finance:no_records" in " ".join(first.known_missing_sources)


def test_snapshot_builder_is_read_only(tmp_path):
    sources = _sources(tmp_path)
    sources.root.mkdir(parents=True)
    before = tuple(sources.root.rglob("*"))
    _snapshot(tmp_path)
    assert tuple(sources.root.rglob("*")) == before


def test_finance_records_remain_references_and_unknown_contribution_stays_unknown(tmp_path):
    sources = _sources(tmp_path)
    store = FinanceStore(sources.finance)
    store.put_all((_cost(), _revenue(), _proposal()))
    snapshot = _snapshot(tmp_path)
    section = snapshot.section("finance")
    assert section.dimension("known_cost").value == ("12.5 EUR",)
    assert section.dimension("known_revenue").value == ("30 EUR",)
    assert section.dimension("known_contribution").known is False
    assert section.dimension("cost_per_accepted_deliverable").known is False
    assert len(snapshot.decision_queue) == 1
    item = snapshot.decision_queue[0]
    assert "large_or_recurring_paid_api_spend" in item.reserved_actions
    assert item.evidence_refs == ("finance:spend_proposal:spend.001",)
    payload = snapshot.to_dict()
    assert not any("estimated_amount" in ref for ref in payload["source_refs"])


def test_runtime_rejected_usage_and_context_metrics_are_visible(tmp_path):
    sources = _sources(tmp_path)
    ResourceUsageStore(sources.execution).append(ResourceUsageRecord(
        task_id="task-rejected", reasoning_class=ReasoningClass.C,
        outcome=Outcome.REJECTED, rejection_reason="receipt failed validation",
        context_sources=("company/runtime", "company/finance"),
        initial_context_sources=("company/runtime",),
        expanded_context_sources=("company/finance",),
        rejected_expansion_sources=("production/secrets",),
        context_refs_used=("company/runtime", "company/finance"),
        context_usage_reported=True, expansion_count=1,
        expansion_ledger_fingerprint="a" * 16, retries=1,
    ))
    snapshot = _snapshot(tmp_path)
    execution = snapshot.section("execution")
    assert execution.dimension("rejected_attempts").value == 1
    assert execution.dimension("retries").value == 1
    assert execution.dimension("context_precision").value == 1.0
    assert execution.dimension("reported_context_expansions").value == 1
    assert execution.dimension("reported_rejected_expansion_refs").value == 1
    assert any(item.subject == "task-rejected" for item in snapshot.attention_items)


def test_orphan_execution_packet_is_reported_not_repaired(tmp_path):
    sources = _sources(tmp_path)
    config = load_company_config(ROOT / "company")
    plan = plan_task(TaskSpecification(
        task_id="orphan-task", objective="Prove an orphan packet is visible.",
        required_capabilities=("software_architecture",),
        deterministic_execution_possible=True,
        context=ContextRequirements(refs=(ContextRef(ContextKind.FILE, "company/README.md",
                                                       "Company OS boundary"),),
                                    acceptance_criteria=("The orphan packet appears as an integrity issue.",)),
    ), config)
    packet = build_session_packet(plan, expected_branch="test-dashboard")
    ExecutionStore(sources.execution).append_packet(packet)
    snapshot = _snapshot(tmp_path)
    execution = snapshot.section("execution")
    assert execution.dimension("pending_receipts").value == 1
    assert any("orphan packet without authority" in issue for issue in execution.integrity_issues)
    assert any(item.attention_id == "execution-pending-receipts" for item in snapshot.attention_items)


def test_research_stopped_batch_is_visible(tmp_path):
    sources = _sources(tmp_path)
    batch = open_batch(id="batch-one", objective="Bounded research sweep.", created=TODAY,
                       owner="research-owner", query_ids=("query-one",),
                       budget=BatchBudget(max_queries=2),
                       stop_conditions=(StopCondition(StopReason.MAX_QUERIES, threshold=2),))
    batch = stop_batch(batch, on=TODAY, by="research-owner", reason="Manual stop for review.")
    ResearchStore(sources.research).add(batch)
    snapshot = _snapshot(tmp_path)
    assert snapshot.section("research").dimension("stopped_batches").value == 1
    assert any(item.attention_id == "research-stopped-batch-one" for item in snapshot.attention_items)


def test_workforce_dormant_is_distinct_from_missing(tmp_path):
    snapshot = _snapshot(tmp_path)
    workforce = snapshot.section("workforce")
    assert workforce.availability is Availability.AVAILABLE
    assert workforce.dimension("dormant_employees").known is True
    assert workforce.dimension("dormant_employees").value > 0
    assert "workforce:no_records" not in snapshot.known_missing_sources


def _manual_snapshot(*, day: dt.date = TODAY, stale: bool = False,
                     decision_state: str = "proposed", fingerprint: str = "a" * 16) -> CompanyStateSnapshot:
    freshness = FreshnessState.STALE if stale else FreshnessState.CURRENT
    ref = SourceReference(SourceSubsystem.ANALYTICS, "result", "result-1",
                          "analytics/results/result-1.json", fingerprint, freshness,
                          TODAY - dt.timedelta(days=1) if stale else TODAY + dt.timedelta(days=1))
    decision = CEODecisionItem("decision-1", "architecture", SourceSubsystem.ANALYTICS,
                               "major architecture merge", "CEO-reserved action requires attention.",
                               (ref.key,), risk="high", reversibility="reversible_with_cost",
                               current_state=decision_state,
                               reserved_actions=("merge_major_architecture_rewrite",))
    attention = AttentionItem("attention-1", "experiment-1", "Result is inconclusive.",
                              (ref.key,), "analytics", AttentionLevel.WATCH,
                              "Collect the named missing observation.")
    sections = tuple(ExecutiveSection(name, Availability.AVAILABLE, f"{name} summary",
                                      (ExecutiveDimension("records", 1, source_refs=(ref.key,)),),
                                      (ref.key,)) for name in
                     ("execution", "research", "analytics", "finance", "workforce", "organization", "system"))
    return CompanyStateSnapshot(f"snapshot-{day.isoformat()}-{decision_state}-{fingerprint[0]}", day, day,
                                (ref,), sections, stale_sources=(ref.key,) if stale else (),
                                decision_queue=(decision,), attention_items=(attention,))


def test_stale_evidence_is_explicit_and_integrity_matches_it():
    snapshot = _manual_snapshot(stale=True)
    assert snapshot.source_refs[0].freshness is FreshnessState.STALE
    assert snapshot.stale_sources == (snapshot.source_refs[0].key,)
    assert check_integrity(snapshot) == ()


def test_decision_and_attention_order_are_transparent_and_deterministic():
    ref = _manual_snapshot().source_refs[0]
    normal = CEODecisionItem("z", "spend", SourceSubsystem.FINANCE, "normal", "needs approval",
                             (ref.key,), risk="low", reserved_actions=("large_or_recurring_paid_api_spend",))
    blocked = CEODecisionItem("a", "spend", SourceSubsystem.FINANCE, "blocked", "cannot proceed",
                              (ref.key,), risk="high", reserved_actions=("large_or_recurring_paid_api_spend",), blocked=True)
    base = _manual_snapshot()
    snapshot = CompanyStateSnapshot("ordered", TODAY, TODAY, base.source_refs, base.sections,
                                    decision_queue=(normal, blocked), attention_items=base.attention_items)
    assert [x.decision_id for x in snapshot.decision_queue] == ["a", "z"]
    assert not hasattr(snapshot.decision_queue[0], "priority_score")


def test_snapshot_diff_compares_structured_identity_and_state():
    old = _manual_snapshot(day=TODAY, decision_state="proposed", fingerprint="a" * 16)
    new = _manual_snapshot(day=TODAY + dt.timedelta(days=1), decision_state="under_review", fingerprint="b" * 16)
    delta = diff_snapshots(old, new)
    categories = {change.category for change in delta.changes}
    assert "source_changed" in categories
    assert "decision_state_changed" in categories
    assert all("significant" not in change.category for change in delta.changes)


def test_snapshot_diff_refuses_reverse_chronology():
    with pytest.raises(DashboardError, match="chronology"):
        diff_snapshots(_manual_snapshot(day=TODAY), _manual_snapshot(day=TODAY - dt.timedelta(days=1)))


def test_compact_brief_is_deterministic_and_contains_no_raw_record_body():
    snapshot = _manual_snapshot()
    first = build_brief(snapshot)
    assert first == build_brief(snapshot)
    text = first.render_text()
    assert "Needs my decision" in text and "major architecture merge" in text
    assert "canonical" not in text.lower()
    assert len(text) < 3000


def test_derived_store_is_append_only_and_round_trips(tmp_path):
    snapshot = _manual_snapshot()
    brief = build_brief(snapshot)
    store = DashboardStore(tmp_path)
    first = store.put_snapshot(snapshot)
    assert store.put_snapshot(snapshot) == first
    assert store.put_brief(brief).is_file()
    assert store.get_snapshot(snapshot.snapshot_id) == snapshot
    first.write_text("{}", encoding="utf-8")
    with pytest.raises(DashboardError, match="refusing to overwrite"):
        store.put_snapshot(snapshot)


@pytest.mark.parametrize("method", ("approve", "reject", "merge", "hire", "spend", "publish", "archive"))
def test_dashboard_exposes_no_company_action_methods(method):
    for cls in (CompanyStateSnapshot, CEODecisionItem, AttentionItem, DashboardStore):
        assert not hasattr(cls, method)


def test_no_global_verdict_or_winner_fields_exist():
    names = {field.name for field in fields(CompanyStateSnapshot)}
    assert not names.intersection({"company_health_score", "CEO_score", "overall_score",
                                   "company_grade", "traffic_light_score", "format_winner", "project_winner"})
    text = _manual_snapshot().canonical_json().lower()
    for banned in ("company_health_score", "overall_score", "company_grade", "format_winner", "project_winner"):
        assert banned not in text


def test_attention_requires_a_resolution_condition():
    ref = _manual_snapshot().source_refs[0]
    with pytest.raises(DashboardError, match="resolves_when"):
        AttentionItem("bad", "subject", "reason", (ref.key,), "system", AttentionLevel.WATCH, "")


def test_decision_requires_a_source_reference():
    with pytest.raises(DashboardError, match="no source"):
        CEODecisionItem("bad", "spend", SourceSubsystem.FINANCE, "service", "why", ())


def test_analytics_association_language_stays_noncausal():
    section = ExecutiveSection("analytics", Availability.AVAILABLE, "association only",
                               (ExecutiveDimension("association_only_results", 1,
                                                   note="These results explicitly do not establish causation."),))
    assert "do not establish causation" in section.dimension("association_only_results").note
    assert "caused" not in section.summary


def test_integrity_reports_ceo_item_without_reserved_action_evidence():
    base = _manual_snapshot()
    bad = CEODecisionItem("bad", "spend", SourceSubsystem.FINANCE, "service", "CEO needed",
                          (base.source_refs[0].key,))
    snapshot = CompanyStateSnapshot("bad", TODAY, TODAY, base.source_refs, base.sections,
                                    decision_queue=(bad,))
    assert any("reserved-action evidence" in issue for issue in check_integrity(snapshot))


def test_integrity_rejects_canonical_record_bodies_inside_dimensions():
    base = _manual_snapshot()
    bad_section = ExecutiveSection("analytics", Availability.AVAILABLE, "bad",
                                   (ExecutiveDimension("raw_result", {"result_id": "copied"}),),
                                   (base.source_refs[0].key,))
    sections = tuple(bad_section if section.name == "analytics" else section
                     for section in base.sections)
    snapshot = CompanyStateSnapshot("bad-body", TODAY, TODAY, base.source_refs, sections)
    assert any("contains an object body" in issue for issue in check_integrity(snapshot))


def test_dashboard_imports_no_production_package():
    for path in sorted((ROOT / "company/dashboard").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(name == "production" or name.startswith("production.") for name in imported)


def test_capsule_is_bounded_and_control_plane_stays_at_eight_with_full_closure():
    index = CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds")
    dashboard = index.get("company-ceo-dashboard")
    control = index.get("company-os-control-plane")
    assert dashboard.size_chars() <= 4000
    assert len(control.dependencies) <= 8
    assert "company-ceo-dashboard" in control.dependencies
    assert "company-research-intelligence" not in control.dependencies
    assert "company-research-intelligence" in index.dependency_closure("company-os-control-plane")
    assert index.dependency_closure("company-os-control-plane") == tuple(sorted(set(index.ids()) - {"company-os-control-plane"}))
    assert _dependency_cycles(index) == ()
    assert index.integrity(repo_root=ROOT) == ()


def test_system_view_has_no_runtime_validation_cycle(tmp_path):
    system = _snapshot(tmp_path).section("system")
    assert not any("company-runtime" in issue and "company-validation" in issue
                   and "cycle" in issue for issue in system.integrity_issues)


def test_cli_model_uses_only_standard_library_and_internal_dependencies():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "dashboard" not in requirements.lower()

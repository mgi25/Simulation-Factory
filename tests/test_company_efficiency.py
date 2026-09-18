from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from company.efficiency import (
    GRAPHIFY_STATUS,
    RTK_STATUS,
    BenchmarkMode,
    CodeIntelligenceQuery,
    CodeQueryKind,
    CostMeasurement,
    EfficiencyError,
    EfficiencyRecord,
    EfficiencyStore,
    MeasurementSource,
    ReferenceRepositoryProvider,
    ReuseTier,
    TokenMeasurement,
    capture_tool_output,
    check_reuse,
    compare_efficiency,
    estimate_tokens,
    normalise_provider_usage,
    summarise_efficiency,
)
from company.efficiency.audit import (
    WasteCategory,
    WasteFinding,
    WasteSeverity,
    WorkflowAudit,
    audit_workflow,
)
from company.efficiency.routing import (
    ModelRoutingPolicy,
    ModelRoutingRule,
    ModelTier,
    default_routing_policy,
)
from company.efficiency.strategy import (
    CostPerAcceptedResult,
    ExecutionStrategy,
    StrategyKind,
    compute_cost_per_result,
    select_strategy,
)
from company.efficiency.tool_evaluation import (
    ToolEvaluation,
    ToolEvaluationReport,
    ToolVerdict,
    evaluate_tools,
)
from company.efficiency.benchmark import BenchmarkRunner, default_scenarios
from company.efficiency.__main__ import main as efficiency_main
from company.runtime import ExecutionStoreError
from ai_platform.resource_classes import (
    ReasoningClass,
    TaskSignals,
    classify,
)
from knowledge.company_os.capsules import (
    DEFAULT_BUDGET,
    CapsuleIndex,
    TaskQuery,
    select_capsules,
)


ROOT = Path(__file__).resolve().parents[1]


def _record(**changes) -> EfficiencyRecord:
    record = EfficiencyRecord(
        run_id="run-1",
        task_id="task-1",
        mode=BenchmarkMode.CAPSULE_OPTIMIZED,
        capabilities_selected=("capability_context_assembly",),
        capsules_selected=("company-runtime",),
        capsule_count=1,
        capsule_chars=100,
        context_chars=120,
        context_bytes=120,
        context_manifest_fingerprint="0123456789abcdef",
        execution_packet_chars=60,
        execution_packet_bytes=70,
        repository_references_selected=("company/runtime/context_assembly.py",),
        repository_files_read=("company/runtime/context_assembly.py",),
        tool_calls=1,
        tool_output_chars=20,
        tool_output_bytes=20,
        tool_context_chars=20,
        tool_context_bytes=20,
        tokens=TokenMeasurement.provider_reported(input_tokens=10, output_tokens=5),
        cache_hits=0,
        cache_misses=1,
        context_expansion_requests=0,
        context_expansion_approvals=0,
        context_expansion_denials=0,
        latency_ms=None,
        model="provider/model",
        cost=CostMeasurement.unavailable("no reviewed rate"),
        minimalism=check_reuse(ReuseTier.SMALL_IMPLEMENTATION, "small boundary required"),
        integrations=(GRAPHIFY_STATUS, RTK_STATUS),
    )
    return replace(record, **changes)


def test_research_core_is_selective_and_operations_pull_it_as_a_dependency() -> None:
    index = CapsuleIndex.load()
    core = select_capsules(
        index,
        TaskQuery(capabilities=("capability_reference_analysis",)),
    )
    operations = select_capsules(
        index,
        TaskQuery(capabilities=("capability_research_ingestion",)),
    )
    assert "company-research-intelligence" in core.ids()
    assert "company-research-operations" not in core.ids()
    assert operations.ids()[0] == "company-research-operations"
    assert "company-research-intelligence" in operations.ids()
    assert operations.ids() == select_capsules(
        index,
        TaskQuery(capabilities=("capability_research_ingestion",)),
    ).ids()


def test_research_split_is_semantic_bounded_and_not_exactly_duplicated() -> None:
    index = CapsuleIndex.load()
    core = index.get("company-research-intelligence")
    operations = index.get("company-research-operations")
    assert "company-research-intelligence" in operations.dependencies
    assert "company-research-operations" not in core.dependencies
    assert set(core.capabilities).isdisjoint(operations.capabilities)
    assert set(core.invariants).isdisjoint(operations.invariants)
    assert core.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    assert operations.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    assert len(core.dependencies) == len(set(core.dependencies))
    assert len(operations.dependencies) == len(set(operations.dependencies))


def test_efficiency_code_routes_through_the_existing_runtime_capsule() -> None:
    index = CapsuleIndex.load()
    assert [capsule.id for capsule in index.by_path("company/efficiency/benchmark.py")] == [
        "company-runtime"
    ]
    selected = select_capsules(
        index,
        TaskQuery(capabilities=("capability_efficiency_benchmark",)),
    )
    assert selected.ids()[0] == "company-runtime"


def test_token_provenance_never_turns_unavailable_into_zero() -> None:
    unavailable = TokenMeasurement.unavailable("provider omitted usage")
    assert unavailable.source is MeasurementSource.UNAVAILABLE
    assert unavailable.total_tokens is None
    estimated = estimate_tokens("five bytes")
    assert estimated.source is MeasurementSource.ESTIMATED
    assert estimated.method == "ceil(utf8_bytes/4)"
    reported = TokenMeasurement.provider_reported(input_tokens=4, output_tokens=3)
    assert reported.source is MeasurementSource.PROVIDER_REPORTED
    assert reported.total_tokens == 7
    with pytest.raises(EfficiencyError, match="cannot carry counts"):
        TokenMeasurement(MeasurementSource.UNAVAILABLE, input_tokens=0, reason="missing")


def test_provider_usage_adapter_preserves_reported_values_and_safe_totals() -> None:
    openai = normalise_provider_usage(
        {
            "provider": "openai",
            "model": "example-model",
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
            "latency_ms": 250,
            "cost": {"amount": "0.012", "currency": "USD"},
        }
    )
    assert openai.tokens.source is MeasurementSource.PROVIDER_REPORTED
    assert (
        openai.tokens.input_tokens,
        openai.tokens.output_tokens,
        openai.tokens.total_tokens,
    ) == (11, 7, 18)
    assert openai.provider == "openai" and openai.model == "example-model"
    assert openai.cost.source is MeasurementSource.PROVIDER_REPORTED

    anthropic = normalise_provider_usage(
        {"usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 999}}
    )
    assert anthropic.tokens.total_tokens == 8  # invalid total cannot poison the record

    missing = normalise_provider_usage(None)
    assert missing.tokens.source is MeasurementSource.UNAVAILABLE
    assert missing.tokens.total_tokens is None
    assert missing.cost.source is MeasurementSource.UNAVAILABLE


def test_comparison_handles_real_values_unavailable_values_and_zero() -> None:
    baseline = _record(
        run_id="base", mode=BenchmarkMode.BASELINE, context_chars=200,
        repository_files_read=("a", "b"),
    )
    optimized = _record(run_id="opt", context_chars=100, repository_files_read=("a",))
    comparison = compare_efficiency(baseline, optimized)
    assert comparison.context_reduction_pct == 50.0
    assert comparison.repository_read_reduction_pct == 50.0

    unknown = TokenMeasurement.unavailable("not exposed")
    empty = replace(baseline, context_chars=0, repository_files_read=(), tokens=unknown)
    other = replace(optimized, tokens=unknown)
    comparison = compare_efficiency(empty, other)
    assert comparison.context_reduction_pct is None
    assert comparison.token_reduction_pct is None
    assert comparison.repository_read_reduction_pct is None


def test_benchmark_covers_required_scenarios_and_warm_cache() -> None:
    scenarios = default_scenarios()
    assert {scenario.name for scenario in scenarios} == {
        "small_one_capsule", "dependency_closure", "research_task",
        "repository_task", "context_expansion", "warm_cache",
    }
    report = BenchmarkRunner(ROOT).run(
        scenarios,
        modes=(BenchmarkMode.BASELINE, BenchmarkMode.CAPSULE_OPTIMIZED),
    )
    small = next(
        record for record in report.records
        if record.run_id == "small_one_capsule:capsule_optimized:1"
    )
    assert small.capsule_count == 1
    research = next(
        record for record in report.records
        if record.run_id == "research_task:capsule_optimized:1"
    )
    assert "company-research-operations" not in research.capsules_selected
    expansion = next(
        record for record in report.records
        if record.run_id == "context_expansion:capsule_optimized:1"
    )
    assert (expansion.context_expansion_requests, expansion.context_expansion_approvals,
            expansion.context_expansion_denials) == (2, 1, 1)
    assert expansion.repository_files_read == ("intelligence/research/reference_case.py",)
    warm = [
        record for record in report.records
        if record.task_id == "warm_cache"
        and record.mode is BenchmarkMode.CAPSULE_OPTIMIZED
    ]
    assert [(record.cache_hits, record.cache_misses) for record in warm] == [(0, 1), (1, 0)]


def test_code_intelligence_falls_back_without_graphify() -> None:
    provider = ReferenceRepositoryProvider(ROOT)
    result = provider.query(
        CodeIntelligenceQuery(
            CodeQueryKind.LIKELY_FILES,
            "context",
            candidate_paths=("company/runtime/context_assembly.py", "../outside"),
        )
    )
    assert result.available
    assert result.references == ("company/runtime/context_assembly.py",)
    symbols = provider.query(CodeIntelligenceQuery(CodeQueryKind.SYMBOLS, "assemble_context"))
    assert not symbols.available
    assert not GRAPHIFY_STATUS.available and not GRAPHIFY_STATUS.enabled


def test_tool_output_boundary_preserves_raw_output_with_and_without_compression(tmp_path) -> None:
    raw = "ok\nok\nwarning\nfailed"
    normal = capture_tool_output(task_id="task-1", command="test", exit_status=1, raw_output=raw)
    assert normal.context_output == raw
    assert not normal.compressed
    assert not RTK_STATUS.available

    class SummaryCompressor:
        name = "fixture"

        def compress(self, raw_output: str) -> str:
            return "warning\nfailed"

    compressed = capture_tool_output(
        task_id="task-1", command="test", exit_status=1, raw_output=raw,
        compressor=SummaryCompressor(),
    )
    store = EfficiencyStore(tmp_path)
    store.append_tool_output(compressed)
    restored = store.tool_outputs("task-1")[0]
    assert restored.raw_output == raw
    assert restored.context_output == "warning\nfailed"
    assert restored.raw_bytes > restored.context_bytes


def test_efficiency_telemetry_is_append_only_and_does_not_change_the_record(tmp_path) -> None:
    store = EfficiencyStore(tmp_path)
    record = _record()
    before = record.fingerprint()
    first = store.append(record)
    second = store.append(record)
    assert first.attempt == 1 and second.attempt == 2
    assert record.fingerprint() == before
    assert [item.fingerprint() for item in store.records("task-1")] == [before, before]
    assert store.history("task-1")["efficiency"][0]["total_tokens"] == 15


def test_efficiency_store_rejects_a_false_execution_link(tmp_path) -> None:
    store = EfficiencyStore(tmp_path)
    linked = replace(_record(), packet_fingerprint="0123456789abcdef", packet_attempt=1)
    with pytest.raises(ExecutionStoreError, match="persisted packet attempt"):
        store.append(linked)


def test_finalized_efficiency_append_is_idempotent_and_conflicts_are_refused(
    tmp_path,
) -> None:
    store = EfficiencyStore(tmp_path)
    record = _record(run_id="execution:stable")
    first = store.append_idempotent(record)
    second = store.append_idempotent(record)
    assert first == second
    assert len(store.records(record.task_id)) == 1
    with pytest.raises(ExecutionStoreError, match="different telemetry"):
        store.append_idempotent(replace(record, context_bytes=121))
    assert len(store.records(record.task_id)) == 1


def test_real_efficiency_cli_filters_and_summarises_json(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    EfficiencyStore(tmp_path).append(_record(mode=BenchmarkMode.REAL))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "python -m company.efficiency",
            "real",
            "--state-dir",
            str(tmp_path),
            "--capability",
            "capability_context_assembly",
        ],
    )
    assert efficiency_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["total_runs"] == 1
    assert payload["records"][0]["mode"] == "real"


def test_summary_is_dashboard_ready_without_fabricating_cost() -> None:
    summary = summarise_efficiency((
        _record(run_id="base", mode=BenchmarkMode.BASELINE, context_chars=200),
        _record(run_id="opt", context_chars=100, cache_hits=1, cache_misses=0),
    ))
    assert summary.total_runs == 2
    assert summary.average_context_reduction_pct == 50.0
    assert summary.cache_hit_rate == 0.5
    assert summary.token_source is MeasurementSource.PROVIDER_REPORTED
    assert summary.provider_reported_token_runs == 2
    assert summary.cost_amount is None

    mixed = summarise_efficiency((
        _record(run_id="reported"),
        _record(run_id="estimated", tokens=estimate_tokens("context")),
    ))
    assert mixed.average_input_tokens is None
    assert mixed.token_source is None
    assert mixed.average_provider_input_tokens == 10
    assert mixed.average_estimated_input_tokens == 2

    failed = summarise_efficiency((
        _record(run_id="failed", outcome="rejected"),
    ))
    assert failed.failures_with_measurable_spend == 1


def test_minimalism_check_requires_every_cheaper_reuse_tier() -> None:
    check = check_reuse(ReuseTier.SMALL_IMPLEMENTATION, "bounded implementation needed")
    assert check.created_new_code
    assert check.considered_tiers[-1] is ReuseTier.SMALL_IMPLEMENTATION
    with pytest.raises(EfficiencyError, match="every cheaper"):
        replace(check, considered_tiers=(ReuseTier.SMALL_IMPLEMENTATION,))


# --- V2: workflow audit ---------------------------------------------------


def test_workflow_audit_produces_findings_with_measured_evidence() -> None:
    audit = audit_workflow()
    assert audit.total_findings > 0
    assert audit.total_findings == len(audit.findings)
    assert (
        audit.high_severity_count + audit.medium_severity_count + audit.low_severity_count
        == audit.total_findings
    )
    assert audit.high_severity_count >= 2  # context + model routing
    assert audit.estimated_savings_pct > 0
    for finding in audit.findings:
        assert finding.description.strip()
        assert finding.rule.strip()
        assert finding.measured_impact.strip()


def test_workflow_audit_covers_required_waste_categories() -> None:
    audit = audit_workflow()
    categories = {finding.category for finding in audit.findings}
    assert WasteCategory.OVERSIZED_CONTEXT in categories
    assert WasteCategory.OVERPOWERED_MODEL in categories
    assert WasteCategory.UNNECESSARY_MODEL_CALL in categories
    assert WasteCategory.CACHE_MISS in categories


def test_waste_finding_rejects_empty_fields() -> None:
    with pytest.raises(ValueError, match="description"):
        WasteFinding(
            category=WasteCategory.OVERSIZED_CONTEXT,
            severity=WasteSeverity.HIGH,
            description="",
            rule="test",
            measured_impact="test",
            recommendation="test",
        )


# --- V2: model routing policy ---------------------------------------------


def test_routing_policy_maps_every_reasoning_class() -> None:
    policy = default_routing_policy()
    for code in ReasoningClass:
        rule = policy.route(code)
        assert isinstance(rule, ModelRoutingRule)
        assert rule.reasoning_class is code


def test_routing_policy_prefers_deterministic_for_class_a_and_b() -> None:
    policy = default_routing_policy()
    assert policy.route(ReasoningClass.A).tier is ModelTier.DETERMINISTIC
    assert policy.route(ReasoningClass.B).tier is ModelTier.RETRIEVAL
    assert policy.route(ReasoningClass.A).relative_cost_per_token == 0.0
    assert policy.route(ReasoningClass.B).relative_cost_per_token == 0.0


def test_routing_policy_escalates_cost_with_reasoning_depth() -> None:
    policy = default_routing_policy()
    costs = [policy.route(code).relative_cost_per_token for code in ReasoningClass]
    # Each class must cost >= the previous one
    for i in range(1, len(costs)):
        assert costs[i] >= costs[i - 1]


def test_routing_policy_cost_per_accepted_result_accounts_for_retries() -> None:
    policy = default_routing_policy()
    fast = policy.route(ReasoningClass.C)
    capable = policy.route(ReasoningClass.D)
    # Fast model is cheaper per token but less reliable
    assert fast.relative_cost_per_token < capable.relative_cost_per_token
    # Cost per accepted result accounts for first_pass_rate
    assert fast.expected_cost_per_accepted_result() > 0
    assert capable.expected_cost_per_accepted_result() > 0


def test_routing_policy_summary_counts_deterministic_classes() -> None:
    policy = default_routing_policy()
    summary = policy.summary()
    assert summary["deterministic_classes"] == 2  # A and B
    assert summary["model_classes"] == 4  # C, D, E, F
    assert summary["total_classes"] == 6


def test_routing_rule_rejects_invalid_first_pass_rate() -> None:
    with pytest.raises(ValueError, match="expected_first_pass_rate"):
        ModelRoutingRule(
            reasoning_class=ReasoningClass.C,
            tier=ModelTier.FAST,
            rule_name="test",
            reason="test",
            expected_first_pass_rate=1.5,
            relative_cost_per_token=1.0,
            max_context_refs=12,
        )


# --- V2: execution strategy selection ------------------------------------


def test_strategy_selects_deterministic_for_class_a() -> None:
    signals = TaskSignals(deterministic_solution_exists=True)
    classification = classify(signals)
    strategy = select_strategy(classification)
    assert strategy.strategy is StrategyKind.DETERMINISTIC
    assert strategy.expected_cost_per_accepted_result == 0.0


def test_strategy_selects_lightweight_for_class_c_first_attempt() -> None:
    signals = TaskSignals()  # defaults to class C
    classification = classify(signals)
    strategy = select_strategy(classification, prior_attempts=0)
    assert strategy.strategy is StrategyKind.LIGHTWEIGHT_REASONING
    assert strategy.routing_rule.tier is ModelTier.FAST


def test_strategy_escalates_on_retry() -> None:
    signals = TaskSignals()  # class C
    classification = classify(signals)
    first = select_strategy(classification, prior_attempts=0)
    retry = select_strategy(classification, prior_attempts=1)
    assert first.strategy is StrategyKind.LIGHTWEIGHT_REASONING
    assert retry.strategy is StrategyKind.FULL_REASONING
    assert retry.routing_rule.tier is ModelTier.CAPABLE


def test_strategy_uses_cache_when_available() -> None:
    signals = TaskSignals()
    classification = classify(signals)
    strategy = select_strategy(classification, has_cache_hit=True)
    assert strategy.strategy is StrategyKind.CACHED_RETRIEVAL
    assert strategy.cache_eligible


def test_strategy_selects_full_reasoning_for_specialist_tasks() -> None:
    signals = TaskSignals(
        requires_judgment=True,
        specialist_domain="software_engineering",
    )
    classification = classify(signals)
    assert classification.code is ReasoningClass.D
    strategy = select_strategy(classification)
    assert strategy.strategy is StrategyKind.FULL_REASONING
    assert strategy.routing_rule.tier is ModelTier.CAPABLE


def test_cost_per_accepted_result_is_the_headline_metric() -> None:
    result = compute_cost_per_result(
        task_id="wo-test-task",
        total_attempts=2,
        accepted_attempt=2,
        total_input_tokens=50000,
        total_output_tokens=10000,
        total_cost_amount="0.15",
        total_cost_currency="USD",
        model_tiers_used=("fast", "capable"),
        strategy_used=StrategyKind.FULL_REASONING,
    )
    assert not result.first_pass_success
    assert result.retry_overhead_pct == 50.0
    assert result.total_attempts == 2


def test_cost_per_accepted_result_first_pass_success() -> None:
    result = compute_cost_per_result(
        task_id="wo-test-simple",
        total_attempts=1,
        accepted_attempt=1,
    )
    assert result.first_pass_success
    assert result.retry_overhead_pct == 0.0


# --- V2: tool evaluation -------------------------------------------------


def test_tool_evaluation_covers_all_mentioned_tools() -> None:
    report = evaluate_tools()
    tool_names = {e.tool_name for e in report.evaluations}
    assert len(report.evaluations) >= 7
    # The work order mentions these tools explicitly
    assert any("RTK" in name for name in tool_names)
    assert any("Graphify" in name for name in tool_names)
    assert any("ast-grep" in name for name in tool_names)
    assert any("Serena" in name for name in tool_names)
    assert any("Context7" in name for name in tool_names)
    assert any("Ponytail" in name or "minimalism" in name for name in tool_names)


def test_tool_evaluation_no_adoption_without_measured_evidence() -> None:
    report = evaluate_tools()
    for evaluation in report.evaluations:
        assert evaluation.measured_reason.strip()
        if evaluation.verdict is ToolVerdict.ADOPTED:
            # Adopted tools must reference existing implementation
            assert "implemented" in evaluation.measured_reason.lower() or \
                   "already" in evaluation.measured_reason.lower()


def test_tool_evaluation_verdict_counts_match() -> None:
    report = evaluate_tools()
    assert report.adopted_count + report.conditionally_adopted_count + \
        report.deferred_count + report.rejected_count == len(report.evaluations)
    assert report.rejected_count >= 1  # Context7 is rejected


def test_tool_evaluation_context7_rejected_for_measured_reason() -> None:
    report = evaluate_tools()
    context7 = next(e for e in report.evaluations if "Context7" in e.tool_name)
    assert context7.verdict is ToolVerdict.REJECTED
    assert "near zero" in context7.measured_reason.lower()


# --- V2: governance preservation ------------------------------------------


def test_v2_modules_do_not_import_forbidden_paths() -> None:
    """V2 efficiency modules must not import from forbidden governance paths."""
    import ast as ast_module
    v2_modules = (
        ROOT / "company" / "efficiency" / "audit.py",
        ROOT / "company" / "efficiency" / "routing.py",
        ROOT / "company" / "efficiency" / "strategy.py",
        ROOT / "company" / "efficiency" / "tool_evaluation.py",
    )
    forbidden = {"company.integration", "company.validation.no_subagents"}
    violations: list[str] = []
    for source in v2_modules:
        tree = ast_module.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast_module.walk(tree):
            if isinstance(node, ast_module.ImportFrom):
                module = node.module or ""
                if any(module == f or module.startswith(f + ".") for f in forbidden):
                    violations.append(f"{source.name}:{node.lineno}: {module}")
            elif isinstance(node, ast_module.Import):
                for alias in node.names:
                    if any(alias.name == f or alias.name.startswith(f + ".") for f in forbidden):
                        violations.append(f"{source.name}:{node.lineno}: {alias.name}")
    assert violations == []


# --- V2: benchmark integration with V2 metrics ---------------------------


def test_benchmark_report_includes_baseline_vs_optimized_evidence() -> None:
    report = BenchmarkRunner(ROOT).run(
        (next(s for s in default_scenarios() if s.name == "dependency_closure"),),
        modes=(BenchmarkMode.BASELINE, BenchmarkMode.CAPSULE_OPTIMIZED),
    )
    baseline = next(r for r in report.records if r.mode is BenchmarkMode.BASELINE)
    optimized = next(r for r in report.records if r.mode is BenchmarkMode.CAPSULE_OPTIMIZED)
    assert len(report.comparisons) == 1
    comparison = report.comparisons[0]
    # Optimized must use fewer capsules than baseline
    assert optimized.capsule_count <= baseline.capsule_count
    # Reduction percentage must be non-negative when optimized < baseline
    if baseline.context_chars and optimized.context_chars:
        assert comparison.context_reduction_pct is not None
        assert comparison.context_reduction_pct >= 0

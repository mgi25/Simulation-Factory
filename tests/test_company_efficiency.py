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
from company.efficiency.benchmark import BenchmarkRunner, default_scenarios
from company.efficiency.__main__ import main as efficiency_main
from company.runtime import ExecutionStoreError
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


# --- execution strategy selection ------------------------------------------

from ai_platform.resource_classes import ReasoningClass, Risk
from company.efficiency.strategy import (
    CheckpointRule,
    ExecutionStrategy,
    ModelTier,
    OutputReductionDirective,
    ResourceCeiling,
    select_strategy,
)
from company.efficiency.budget import BudgetCheck, check_budget, should_checkpoint
from company.efficiency.baseline import Baseline, BaselineEntry, extract_baseline


def test_strategy_selects_strongest_for_specialist_reasoning() -> None:
    strategy = select_strategy(ReasoningClass.D, Risk.MEDIUM, evidence_required=True)
    assert strategy.model_tier is ModelTier.STRONGEST
    assert strategy.provider_count == 1
    assert "specialist" in strategy.strategy_reason


def test_strategy_selects_standard_for_routine_c_class() -> None:
    strategy = select_strategy(ReasoningClass.C, Risk.LOW)
    assert strategy.model_tier is ModelTier.STANDARD
    assert "routine" in strategy.strategy_reason


def test_strategy_standard_even_with_evidence_required() -> None:
    """evidence_required does not force strongest — only reasoning class and risk do."""
    strategy = select_strategy(ReasoningClass.C, Risk.LOW, evidence_required=True)
    assert strategy.model_tier is ModelTier.STANDARD
    assert "routine" in strategy.strategy_reason


def test_strategy_selects_strongest_for_high_risk() -> None:
    strategy = select_strategy(ReasoningClass.C, Risk.HIGH)
    assert strategy.model_tier is ModelTier.STRONGEST
    assert "risk" in strategy.strategy_reason


def test_strategy_review_has_reduced_context_budget() -> None:
    dev = select_strategy(ReasoningClass.D, Risk.MEDIUM)
    review = select_strategy(ReasoningClass.D, Risk.MEDIUM, is_review=True)
    assert review.context_budget_chars < dev.context_budget_chars
    assert "review" in review.strategy_reason


def test_strategy_is_deterministic() -> None:
    first = select_strategy(ReasoningClass.D, Risk.MEDIUM, max_context_refs=8)
    second = select_strategy(ReasoningClass.D, Risk.MEDIUM, max_context_refs=8)
    assert first == second


def test_strategy_to_dict_is_complete() -> None:
    strategy = select_strategy(ReasoningClass.D, Risk.MEDIUM)
    payload = strategy.to_dict()
    assert payload["model_tier"] == "strongest"
    assert isinstance(payload["context_budget_chars"], int)
    assert isinstance(payload["checkpoint_threshold_chars"], int)
    assert payload["checkpoint_rule"] in {r.value for r in CheckpointRule}
    assert isinstance(payload["output_reduction"], dict)
    assert isinstance(payload["resource_ceiling"], dict)
    assert payload["provider_count"] == 1
    assert payload["strategy_reason"]


def test_output_reduction_standard_omits_passing_tests() -> None:
    standard = OutputReductionDirective.standard()
    assert standard.omit_passing_test_detail is True
    assert standard.omit_clean_git_detail is True
    full = OutputReductionDirective.full()
    assert full.omit_passing_test_detail is False


def test_resource_ceiling_varies_by_tier() -> None:
    standard = ResourceCeiling.for_tier(ModelTier.STANDARD, ReasoningClass.C)
    strongest = ResourceCeiling.for_tier(ModelTier.STRONGEST, ReasoningClass.D)
    assert strongest.max_turns >= standard.max_turns
    assert strongest.max_tool_calls >= standard.max_tool_calls


# --- budget enforcement ----------------------------------------------------


def test_budget_check_detects_violations() -> None:
    strategy = select_strategy(ReasoningClass.C, Risk.LOW)
    ok = check_budget(strategy, context_chars=1000, turns=5, tool_calls=10)
    assert ok.within_budget
    assert not ok.exceeded
    assert ok.violations == ()

    over = check_budget(
        strategy,
        context_chars=strategy.context_budget_chars + 1,
        turns=strategy.resource_ceiling.max_turns + 1,
    )
    assert over.exceeded
    assert len(over.violations) == 2


def test_budget_check_handles_none_values() -> None:
    strategy = select_strategy(ReasoningClass.D, Risk.MEDIUM)
    result = check_budget(strategy)
    assert result.within_budget


def test_checkpoint_respects_critical_section() -> None:
    strategy = select_strategy(ReasoningClass.D, Risk.MEDIUM)
    # Over threshold but in critical section: don't checkpoint
    assert not should_checkpoint(
        strategy,
        context_chars=strategy.checkpoint_threshold_chars + 1000,
        in_critical_section=True,
        has_committed_progress=True,
    )
    # Over threshold, not critical, has progress: checkpoint
    assert should_checkpoint(
        strategy,
        context_chars=strategy.checkpoint_threshold_chars + 1000,
        in_critical_section=False,
        has_committed_progress=True,
    )
    # Under threshold: don't checkpoint
    assert not should_checkpoint(
        strategy,
        context_chars=100,
        has_committed_progress=True,
    )


# --- baseline extraction ---------------------------------------------------


def test_baseline_from_real_efficiency_records(tmp_path) -> None:
    store = EfficiencyStore(tmp_path)
    store.append(_record(
        mode=BenchmarkMode.REAL,
        model="claude-opus-4-6[1m]",
        provider="anthropic",
        outcome="accepted",
        cost=CostMeasurement(
            MeasurementSource.PROVIDER_REPORTED,
            amount="1.50",
            currency="USD",
        ),
    ))
    baseline = extract_baseline(tmp_path)
    assert len(baseline.entries) == 1
    assert baseline.entries[0].task_id == "task-1"
    assert baseline.entries[0].model == "claude-opus-4-6[1m]"
    assert baseline.entries[0].cost_amount == "1.50"
    assert baseline.total_cost_usd == "1.50"
    assert baseline.all_used_strongest_model
    assert len(baseline.state_dirs_read) == 1


def test_baseline_excludes_benchmark_records(tmp_path) -> None:
    store = EfficiencyStore(tmp_path)
    store.append(_record(mode=BenchmarkMode.BASELINE))
    store.append(_record(run_id="run-2", mode=BenchmarkMode.CAPSULE_OPTIMIZED))
    baseline = extract_baseline(tmp_path)
    assert len(baseline.entries) == 0


def test_baseline_handles_missing_state_dir() -> None:
    baseline = extract_baseline("/nonexistent/path")
    assert len(baseline.entries) == 0
    assert baseline.total_cost_usd is None


def test_baseline_to_dict_is_serializable(tmp_path) -> None:
    store = EfficiencyStore(tmp_path)
    store.append(_record(
        mode=BenchmarkMode.REAL,
        outcome="accepted",
    ))
    baseline = extract_baseline(tmp_path)
    payload = baseline.to_dict()
    assert payload["entry_count"] == 1
    serialized = json.dumps(payload)
    assert "task-1" in serialized


def test_baseline_gpt4o_is_not_strongest(tmp_path) -> None:
    """gpt-4o is a mid-tier model; it should not be classified as strongest."""
    store = EfficiencyStore(tmp_path)
    store.append(_record(
        mode=BenchmarkMode.REAL,
        model="gpt-4o",
        provider="openai",
        outcome="accepted",
    ))
    baseline = extract_baseline(tmp_path)
    assert not baseline.all_used_strongest_model


# --- output reduction (applied, not advisory) ---------------------------------

from company.efficiency.strategy import (
    reduce_test_output,
    reduce_log_output,
    reduce_git_output,
    scope_file_listing,
)


def test_reduce_test_output_omits_passing_lines() -> None:
    raw = "PASSED test_one\nPASSED test_two\nFAILED test_three\n=== 2 passed, 1 failed ==="
    directive = OutputReductionDirective.standard()
    reduced = reduce_test_output(raw, directive)
    assert "PASSED test_one" not in reduced
    assert "FAILED" in reduced or "failed" in reduced


def test_reduce_test_output_preserves_all_when_full() -> None:
    raw = "PASSED test_one\nFAILED test_two"
    directive = OutputReductionDirective.full()
    assert reduce_test_output(raw, directive) == raw


def test_reduce_log_output_keeps_tail_and_errors() -> None:
    lines = [f"line {i}" for i in range(200)]
    lines[5] = "ERROR: something failed"
    raw = "\n".join(lines)
    directive = OutputReductionDirective.standard()
    reduced = reduce_log_output(raw, directive)
    assert "ERROR: something failed" in reduced
    assert "line 199" in reduced
    assert len(reduced.splitlines()) < len(lines)


def test_reduce_git_output_clean_tree() -> None:
    raw = "On branch main\nnothing to commit, working tree clean"
    directive = OutputReductionDirective.standard()
    assert reduce_git_output(raw, directive) == "working tree clean"


def test_scope_file_listing_filters_to_allowed_paths() -> None:
    paths = ("company/efficiency/strategy.py", "tools/runner.py", "company/engineering/transport.py")
    allowed = ("company/efficiency", "company/engineering")
    result = scope_file_listing(paths, allowed)
    assert result == ("company/efficiency/strategy.py", "company/engineering/transport.py")


def test_reduce_test_output_all_passing() -> None:
    raw = "PASSED test_one\nPASSED test_two"
    directive = OutputReductionDirective.standard()
    reduced = reduce_test_output(raw, directive)
    assert reduced == "all tests passed"


# --- routine checkpoint rule --------------------------------------------------


def test_routine_job_uses_continue_checkpoint_rule() -> None:
    strategy = select_strategy(ReasoningClass.C, Risk.LOW)
    assert strategy.checkpoint_rule is CheckpointRule.CONTINUE


def test_strongest_job_uses_checkpoint_on_threshold() -> None:
    strategy = select_strategy(ReasoningClass.D, Risk.MEDIUM)
    assert strategy.checkpoint_rule is CheckpointRule.CHECKPOINT_ON_THRESHOLD


# --- AFTER comparison ---------------------------------------------------------

from company.efficiency.baseline import AfterComparison, compare_against_baseline


def test_after_comparison_against_baseline(tmp_path) -> None:
    store = EfficiencyStore(tmp_path)
    store.append(_record(
        mode=BenchmarkMode.REAL,
        model="claude-opus-4-6[1m]",
        provider="anthropic",
        outcome="accepted",
        cost=CostMeasurement(
            MeasurementSource.PROVIDER_REPORTED,
            amount="1.50",
            currency="USD",
        ),
    ))
    baseline = extract_baseline(tmp_path)
    after_record = _record(
        run_id="after-run-1",
        mode=BenchmarkMode.REAL,
        model="claude-sonnet-4-6",
        outcome="accepted",
    )
    comparison = compare_against_baseline(baseline, after_record)
    assert comparison.after_run_id == "after-run-1"
    assert comparison.baseline_entry_count == 1
    assert comparison.baseline_all_strongest
    assert isinstance(comparison.to_dict(), dict)


# --- budget enforcement wired into emission -----------------------------------

from company.efficiency.emission import EfficiencyEmission


def test_emission_includes_budget_check_and_comparison_fields() -> None:
    """EfficiencyEmission carries budget_check and after_comparison fields."""
    assert hasattr(EfficiencyEmission, "budget_check")
    assert hasattr(EfficiencyEmission, "should_checkpoint")
    assert hasattr(EfficiencyEmission, "after_comparison")

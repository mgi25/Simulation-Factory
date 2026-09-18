"""Best-effort efficiency observation at the external-session finalization boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_platform.context_manifest import ContextKind
from ai_platform.resource_classes import ReasoningClass
from ai_platform.serde import dumps
from ai_platform.usage import UsageUnit
from ai_platform.usage import Outcome
from company.runtime.context_expansion import ContextExpansionLedger, ExpansionOutcome
from company.runtime.execution_store import ExecutionRecordPointer, ExecutionStore
from company.runtime.lifecycle import TaskPlan
from company.runtime.packets import SessionPacket
from company.runtime.receipts import SessionReceipt
from knowledge.company_os.capsules import CapsuleIndex

from .providers import (
    GRAPHIFY_STATUS,
    RTK_STATUS,
    ProviderUsage,
    ToolOutputArtifact,
    normalise_provider_usage,
)
from .baseline import AfterComparison, Baseline, compare_against_baseline, extract_baseline
from .budget import BudgetCheck, check_budget, should_checkpoint
from .profile import resource_profile
from .store import EfficiencyStore
from .strategy import ExecutionStrategy, select_strategy
from .telemetry import (
    BenchmarkMode,
    EfficiencyRecord,
    ToolActivity,
    estimate_tokens,
)


@dataclass(frozen=True)
class EfficiencyEmission:
    record: EfficiencyRecord
    pointer: ExecutionRecordPointer
    budget_check: BudgetCheck | None = None
    should_checkpoint: bool = False
    after_comparison: AfterComparison | None = None


def emit_execution_efficiency(
    *,
    plan: TaskPlan,
    packet: SessionPacket,
    packet_attempt: int,
    receipt: SessionReceipt,
    receipt_pointer: ExecutionRecordPointer,
    outcome: Outcome,
    state_dir: str | Path,
    expansion_ledger: ContextExpansionLedger | None,
    tool_outputs: tuple[ToolOutputArtifact, ...] = (),
    capsule_index: CapsuleIndex | None = None,
) -> EfficiencyEmission:
    """Create one real record from facts already present after finalization."""
    if plan.context_manifest is None or plan.context_plan is None:
        raise ValueError("a finalized execution requires a prepared context plan")

    provider_usage = _provider_usage(receipt)
    manifest_text = dumps(plan.context_manifest)
    packet_text = dumps(packet)
    estimated = estimate_tokens(packet_text, receipt.summary)
    ledger = expansion_ledger
    all_refs = packet.context_refs + (ledger.approved_refs if ledger is not None else ())
    selected_files = tuple(ref.ref for ref in all_refs if ref.kind is ContextKind.FILE)
    used_keys = set(receipt.context_refs_used)
    read_files = tuple(
        ref.ref
        for ref in all_refs
        if ref.kind is ContextKind.FILE and ref.key in used_keys
    )
    activities = _tool_activity(tool_outputs)
    raw_chars = _sum_known(activity.raw_chars for activity in activities)
    raw_bytes = _sum_known(activity.raw_bytes for activity in activities)
    context_chars = _sum_known(activity.context_chars for activity in activities)
    context_bytes = _sum_known(activity.context_bytes for activity in activities)
    decisions = ledger.decisions if ledger is not None else ()
    requests = tuple(
        request
        for request in ExecutionStore(state_dir).context_expansion_requests(packet.task_id)
        if request.packet_fingerprint == packet.fingerprint()
        and request.packet_attempt == packet_attempt
    )
    store = EfficiencyStore(state_dir)
    for artifact in tool_outputs:
        store.append_tool_output_idempotent(artifact)

    # Extract baseline BEFORE appending the new record so the current
    # execution is excluded from its own BEFORE baseline.
    pre_baseline: Baseline | None = None
    try:
        pre_baseline = extract_baseline(state_dir)
    except Exception:
        pass

    record = EfficiencyRecord(
        run_id=(
            f"execution:{packet.fingerprint()}:{packet_attempt}:"
            f"receipt:{receipt_pointer.fingerprint}"
        ),
        task_id=packet.task_id,
        mode=BenchmarkMode.REAL,
        capabilities_selected=plan.specification.required_capabilities,
        capsules_selected=plan.context_plan.selected_capsule_ids,
        capsule_count=len(plan.context_plan.selected_capsule_ids),
        capsule_chars=_capsule_chars(plan.context_plan.selected_capsule_ids, capsule_index),
        # The transport passes pointers, not resolved bodies.  Recording the
        # manifest as loaded model context would fabricate observability.
        context_chars=None,
        context_bytes=None,
        context_manifest_fingerprint=plan.context_manifest.fingerprint(),
        execution_packet_chars=len(packet_text),
        execution_packet_bytes=len(packet_text.encode("utf-8")),
        repository_references_selected=selected_files,
        repository_files_read=read_files,
        tool_calls=receipt.usage.tool_calls,
        tool_output_chars=raw_chars,
        tool_output_bytes=raw_bytes,
        tool_context_chars=context_chars,
        tool_context_bytes=context_bytes,
        tokens=provider_usage.tokens,
        cache_hits=receipt.usage.cache_hits,
        cache_misses=receipt.usage.cache_misses,
        context_expansion_requests=max(len(requests), len(decisions)),
        context_expansion_approvals=sum(
            decision.outcome is ExpansionOutcome.APPROVED for decision in decisions
        ),
        context_expansion_denials=sum(
            decision.outcome is ExpansionOutcome.REJECTED for decision in decisions
        ),
        latency_ms=provider_usage.latency_ms,
        model=provider_usage.model,
        cost=provider_usage.cost,
        packet_fingerprint=packet.fingerprint(),
        packet_attempt=packet_attempt,
        integrations=(GRAPHIFY_STATUS, RTK_STATUS),
        estimated_tokens=estimated,
        provider=provider_usage.provider,
        outcome=outcome.value,
        timestamp=receipt.completed_at or None,
        cache_identity=packet.context_cache_key,
        tool_activity=activities,
        context_manifest_chars=len(manifest_text),
        context_manifest_bytes=len(manifest_text.encode("utf-8")),
    )
    pointer = store.append_idempotent(record)

    # --- budget scoring at finalization ---
    #
    # The strategy is re-selected from the plan's **classification**, not from
    # the work order's reasoning-class ceiling. They are different things: the
    # ceiling is the highest class the CEO authorized, the classification is
    # the class the task actually is, and reading the ceiling made every job
    # look like specialist work and therefore recommended the strongest model
    # to every one of them.
    budget_result = None
    checkpoint_needed = False
    after_cmp = None
    try:
        strategy = select_strategy(
            ReasoningClass(plan.classification.resource_class.code.value),
            plan.specification.risk,
            evidence_required=plan.specification.evidence_required,
            max_context_refs=len(packet.context_refs),
            is_review=getattr(packet.path_scope, "read_only", False),
            profile=resource_profile(_profile_name(plan)),
        )
        budget_result = check_budget(
            strategy,
            wall_seconds=receipt.usage.duration_s,
            session_cost=receipt.usage.provider_cost,
            cost_ceiling_enforced=receipt.usage.cost_ceiling_enforced,
            context_chars=len(packet_text) + (record.tool_output_chars or 0),
            input_tokens=receipt.usage.input_units,
            output_tokens=receipt.usage.output_units,
            cache_read_units=receipt.usage.cache_hits or None,
            model_turns=receipt.usage.model_turns,
            repo_file_reads=receipt.usage.repo_file_reads,
            repo_searches=receipt.usage.repo_searches,
            repeated_file_reads=receipt.usage.repeated_file_reads,
            unreliable=receipt.usage.unreliable_metrics,
        )
        checkpoint_needed = should_checkpoint(
            strategy,
            context_chars=len(packet_text) + (record.tool_output_chars or 0),
            in_critical_section=False,
            has_committed_progress=bool(receipt.commit_sha),
        )
    except Exception:
        pass  # budget scoring is observational; failure does not replace the result

    # --- AFTER comparison against pre-extracted baseline ---
    if pre_baseline is not None and pre_baseline.entries:
        try:
            after_cmp = compare_against_baseline(pre_baseline, record)
        except Exception:
            pass

    return EfficiencyEmission(
        record=record,
        pointer=pointer,
        budget_check=budget_result,
        should_checkpoint=checkpoint_needed,
        after_comparison=after_cmp,
    )


def _profile_name(plan: TaskPlan) -> str:
    """The resource profile this task was planned under, or the default.

    Carried in `TaskSpecification.execution`, which is the existing free-form
    slot for execution metadata; a missing key means the default profile,
    because a plan written before profiles existed was executed under whatever
    the company's default then was.
    """
    execution = getattr(plan.specification, "execution", None) or {}
    try:
        return str(execution.get("resource_profile", "") or "")
    except AttributeError:
        return ""


def _provider_usage(receipt: SessionReceipt) -> ProviderUsage:
    usage = receipt.usage
    payload: dict[str, object] = {
        "provider": usage.provider,
        "model": usage.model,
        "latency_ms": usage.provider_latency_ms,
    }
    if usage.usage_unit is UsageUnit.TOKEN:
        payload.update(
            input_tokens=usage.input_units,
            output_tokens=usage.output_units,
        )
    if usage.provider_cost is not None:
        payload.update(cost=usage.provider_cost, currency=usage.provider_cost_currency)
    return normalise_provider_usage(payload)


def _capsule_chars(
    capsule_ids: tuple[str, ...], index: CapsuleIndex | None
) -> int | None:
    selected = index
    if selected is None:
        try:
            selected = CapsuleIndex.load()
        except (OSError, ValueError):
            return None
    try:
        return sum(selected.get(capsule_id).size_chars() for capsule_id in capsule_ids)
    except (KeyError, ValueError):
        return None


def _tool_activity(outputs: tuple[ToolOutputArtifact, ...]) -> tuple[ToolActivity, ...]:
    grouped: dict[str, list[ToolOutputArtifact]] = {}
    for artifact in outputs:
        grouped.setdefault(artifact.command, []).append(artifact)
    return tuple(
        ToolActivity(
            name=name,
            call_count=len(items),
            failure_count=sum(item.exit_status != 0 for item in items),
            raw_chars=sum(item.raw_chars for item in items),
            raw_bytes=sum(item.raw_bytes for item in items),
            context_chars=sum(item.context_chars for item in items),
            context_bytes=sum(item.context_bytes for item in items),
        )
        for name, items in sorted(grouped.items())
    )


def _sum_known(values: object) -> int | None:
    items = tuple(values)  # type: ignore[arg-type]
    return sum(items) if items else None


__all__ = ["EfficiencyEmission", "emit_execution_efficiency"]

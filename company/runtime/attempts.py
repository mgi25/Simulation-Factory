"""Result, handoff, and usage finalisation for a prepared task attempt."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ai_platform.usage import Outcome, ResourceUsageRecord, UsageUnit

from .errors import LifecycleError
from .lifecycle import LifecycleState, TaskPlan
from .tasks import HandoffArtifact, UsageRecordPointer
from .usage_store import ResourceUsageStore


@dataclass(frozen=True)
class AttemptReport:
    outcome: Outcome
    result: str = ""
    evidence: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    changed: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    context_refs_used: tuple[str, ...] = ()
    next_owner: str = ""
    escalation_reason: str = ""
    passes: int = 1
    retries: int = 0
    cache_hits: int = 0
    retrieval_hits: int = 0
    subagents_used: int = 0
    tool_calls: int | None = None
    input_units: int | None = None
    output_units: int | None = None
    usage_unit: UsageUnit = UsageUnit.UNKNOWN
    duration_s: float | None = None
    rejection_reason: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, Outcome):
            raise LifecycleError("attempt outcome must be an Outcome value")
        if not isinstance(self.usage_unit, UsageUnit):
            raise LifecycleError("attempt usage_unit must be a UsageUnit value")
        for name in (
            "evidence",
            "artifacts",
            "changed",
            "unchanged",
            "tests",
            "risks",
            "context_refs_used",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise LifecycleError(
                    f"attempt {name} must be a tuple of non-empty strings"
                )
        for name in (
            "result",
            "next_owner",
            "escalation_reason",
            "rejection_reason",
            "notes",
        ):
            if not isinstance(getattr(self, name), str):
                raise LifecycleError(f"attempt {name} must be a string")


@dataclass(frozen=True)
class AttemptResult:
    usage_record: ResourceUsageRecord
    usage_pointer: UsageRecordPointer
    handoff: HandoffArtifact
    states: tuple[LifecycleState, ...]

    @property
    def state(self) -> LifecycleState:
        return self.states[-1]


def finalise_attempt(
    plan: TaskPlan,
    report: AttemptReport,
    store: ResourceUsageStore,
) -> AttemptResult:
    """Create, persist, and link one attempt's canonical usage record."""
    if (
        not plan.ready
        or plan.selected_employee is None
        or plan.context_manifest is None
        or plan.context_plan is None
    ):
        raise LifecycleError(
            f"task {plan.specification.task_id} is {plan.state.value}, not execution_prepared"
        )
    plan.policy.assert_no_subagents(report.subagents_used)
    if (
        report.outcome is Outcome.ACCEPTED
        and plan.preparation is not None
        and plan.preparation.evidence_required
        and not report.evidence
    ):
        raise LifecycleError(
            f"task {plan.specification.task_id}: accepted result requires evidence"
        )
    manifest = plan.context_manifest
    usage = ResourceUsageRecord(
        task_id=plan.specification.task_id,
        reasoning_class=plan.classification.code,
        outcome=report.outcome,
        context_sources=manifest.keys(),
        context_refs_used=report.context_refs_used,
        context_fingerprint=manifest.fingerprint(),
        explicit_context_sources=plan.context_plan.explicit_refs,
        automatic_context_sources=plan.context_plan.capsule_refs_accepted,
        context_cache_key=plan.context_plan.cache_identity,
        passes=report.passes,
        retries=report.retries,
        cache_hits=report.cache_hits,
        retrieval_hits=report.retrieval_hits,
        subagents_used=report.subagents_used,
        tool_calls=report.tool_calls,
        input_units=report.input_units,
        output_units=report.output_units,
        usage_unit=report.usage_unit,
        duration_s=report.duration_s,
        rejection_reason=report.rejection_reason,
        notes=report.notes,
    )
    status = {
        Outcome.ACCEPTED: "completed",
        Outcome.REJECTED: "blocked",
        Outcome.ABANDONED: "cancelled",
    }[report.outcome]
    handoff_data = {
        "task_id": plan.specification.task_id,
        "owner": plan.selected_employee,
        "objective": plan.specification.objective,
        "status": status,
        "result": report.result,
        "evidence": list(report.evidence),
        "artifacts": list(report.artifacts),
        "changed": list(report.changed),
        "unchanged": list(report.unchanged),
        "tests": list(report.tests),
        "risks": list(report.risks),
        "resource_usage": {
            "record_ref": "resource_usage/pending/000000.json",
            "fingerprint": usage.fingerprint(),
        },
        "next_owner": report.next_owner,
        "escalation": {
            "required": bool(report.escalation_reason.strip()),
            "reason": report.escalation_reason,
        },
    }
    provisional_handoff = HandoffArtifact.from_mapping(
        handoff_data,
        plan.config.task_handoff_schema,
        known_employee_ids=set(plan.config.org_registry["employees"]),
    )
    pointer = store.append(usage)
    states = plan.states + (
        LifecycleState.RESULT_RECORDED,
        LifecycleState.USAGE_RECORDED,
        LifecycleState.USAGE_PERSISTED,
    )
    handoff = replace(provisional_handoff, resource_usage=pointer)
    return AttemptResult(
        usage_record=usage,
        usage_pointer=pointer,
        handoff=handoff,
        states=states + (LifecycleState.HANDOFF_CREATED,),
    )

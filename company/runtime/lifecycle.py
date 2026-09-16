"""Deterministic classification, routing, and execution preparation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.context_manifest import ContextManifest
from ai_platform.policy import BOOTSTRAP_POLICY, ExecutionPolicy
from ai_platform.resource_classes import (
    Classification,
    ReasoningClass,
    classify,
    resource_class,
)
from ai_platform.serde import to_jsonable
from company.validation.bootstrap import validate_agent_contract, validate_bootstrap
from company.validation.no_subagents import enforce_no_subagents
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.ledger import KnowledgeStore

from .config import CompanyConfig, load_company_config
from .context_assembly import (
    ContextAssemblyPolicy,
    ContextPlan,
    assemble_context,
)
from .errors import LifecycleError
from .routing import RoutingResult, match_capabilities
from .specification import TaskSpecification


class LifecycleState(str, Enum):
    SPECIFIED = "specified"
    BOOTSTRAP_VALIDATED = "bootstrap_validated"
    RESOURCE_CLASSIFIED = "resource_classified"
    CAPABILITIES_MATCHED = "capabilities_matched"
    EMPLOYEE_SELECTED = "employee_selected"
    CONTEXT_VALIDATED = "context_validated"
    EXECUTION_PREPARED = "execution_prepared"
    ESCALATED = "escalated"
    RESULT_RECORDED = "result_recorded"
    USAGE_RECORDED = "usage_recorded"
    USAGE_PERSISTED = "usage_persisted"
    HANDOFF_CREATED = "handoff_created"


@dataclass(frozen=True)
class Escalation:
    required: bool = False
    reason: str = ""


@dataclass(frozen=True)
class ExecutionPreparation:
    owner: str
    reasoning_class: ReasoningClass
    context_fingerprint: str
    context_cache_key: str
    evidence_required: bool
    no_subagents: bool
    independent_top_level_parallelism: bool
    same_task_review_is_sequential: bool


@dataclass(frozen=True)
class TaskPlan:
    specification: TaskSpecification
    config: CompanyConfig
    classification: Classification
    routing: RoutingResult
    selected_employee: str | None
    missing_capabilities: tuple[str, ...]
    context_manifest: ContextManifest | None
    context_plan: ContextPlan | None
    preparation: ExecutionPreparation | None
    escalation: Escalation
    states: tuple[LifecycleState, ...]
    policy: ExecutionPolicy

    @property
    def state(self) -> LifecycleState:
        return self.states[-1]

    @property
    def ready(self) -> bool:
        return self.state is LifecycleState.EXECUTION_PREPARED

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.specification.task_id,
            "state": self.state.value,
            "states": [state.value for state in self.states],
            "classification": {
                "reasoning_class": self.classification.code.value,
                "resource_class": self.classification.resource_class.name,
                "rule": self.classification.rule,
                "reason": self.classification.resource_class.intent,
            },
            "routing": self.routing.to_dict(),
            "selected_employee": self.selected_employee,
            "missing_capabilities": list(self.missing_capabilities),
            "context_manifest": (
                to_jsonable(self.context_manifest) if self.context_manifest else None
            ),
            "context_plan": (
                to_jsonable(self.context_plan) if self.context_plan else None
            ),
            "preparation": to_jsonable(self.preparation) if self.preparation else None,
            "escalation": to_jsonable(self.escalation),
        }


def plan_task(
    specification: TaskSpecification,
    config: CompanyConfig | None = None,
    *,
    context_manifest: ContextManifest | None = None,
    employee_contract: Mapping[str, Any] | None = None,
    policy: ExecutionPolicy = BOOTSTRAP_POLICY,
    capsule_index: CapsuleIndex | None = None,
    context_policy: ContextAssemblyPolicy | None = None,
    knowledge_store: KnowledgeStore | None = None,
    observed_source_digests: Mapping[str, str] | None = None,
) -> TaskPlan:
    """Validate, classify, route, select, bound context, and prepare one task."""
    company_config = config or load_company_config()
    states = [LifecycleState.SPECIFIED]
    validate_bootstrap(company_config)
    states.append(LifecycleState.BOOTSTRAP_VALIDATED)

    classification = classify(specification.signals())
    ceiling = resource_class(specification.reasoning_class_ceiling)
    if classification.resource_class.rank > ceiling.rank:
        raise LifecycleError(
            f"task {specification.task_id}: classification {classification.code.value} "
            f"exceeds allowed reasoning class ceiling {ceiling.code.value}; the task "
            "will not be silently downgraded"
        )
    states.append(LifecycleState.RESOURCE_CLASSIFIED)

    routing = match_capabilities(specification.required_capabilities, company_config)
    states.append(LifecycleState.CAPABILITIES_MATCHED)
    eligible = routing.eligible_employee_ids
    if not eligible:
        best = routing.matches[0] if routing.matches else None
        missing = (
            best.missing_capabilities if best else specification.required_capabilities
        )
        reason = "no eligible employee has every required capability"
        if missing:
            reason += "; closest match is missing: " + ", ".join(missing)
        return TaskPlan(
            specification=specification,
            config=company_config,
            classification=classification,
            routing=routing,
            selected_employee=None,
            missing_capabilities=missing,
            context_manifest=None,
            context_plan=None,
            preparation=None,
            escalation=Escalation(True, reason),
            states=tuple(states + [LifecycleState.ESCALATED]),
            policy=policy,
        )

    selected = eligible[0]
    states.append(LifecycleState.EMPLOYEE_SELECTED)
    context = assemble_context(
        specification,
        classification,
        supplied_manifest=context_manifest,
        capsule_index=capsule_index,
        policy=context_policy,
        knowledge_store=knowledge_store,
        observed_source_digests=observed_source_digests,
    )
    manifest = context.manifest
    states.append(LifecycleState.CONTEXT_VALIDATED)

    contract = (
        employee_contract
        if employee_contract is not None
        else _contract_from_registry(selected, company_config)
    )
    validate_agent_contract(contract, company_config)
    if contract.get("employee_id") != selected:
        raise LifecycleError(
            f"employee contract {contract.get('employee_id')!r} does not belong to "
            f"selected employee {selected!r}"
        )
    enforce_no_subagents(specification.execution, path="task.execution")
    policy.assert_no_subagents(0)
    policy.assert_same_task_review_concurrency(1)
    preparation = ExecutionPreparation(
        owner=selected,
        reasoning_class=classification.code,
        context_fingerprint=manifest.fingerprint(),
        context_cache_key=context.plan.cache_identity,
        evidence_required=(
            specification.evidence_required
            or classification.resource_class.requires_evidence
        ),
        no_subagents=policy.no_subagents,
        independent_top_level_parallelism=policy.independent_top_level_parallelism,
        same_task_review_is_sequential=(
            policy.same_task_multi_perspective_review_is_sequential
        ),
    )
    states.append(LifecycleState.EXECUTION_PREPARED)
    return TaskPlan(
        specification=specification,
        config=company_config,
        classification=classification,
        routing=routing,
        selected_employee=selected,
        missing_capabilities=(),
        context_manifest=manifest,
        context_plan=context.plan,
        preparation=preparation,
        escalation=Escalation(),
        states=tuple(states),
        policy=policy,
    )


def _contract_from_registry(employee_id: str, config: CompanyConfig) -> dict[str, Any]:
    contract = deepcopy(config.agent_contract_schema["template"])
    employee = config.org_registry["employees"][employee_id]
    contract.update(
        employee_id=employee_id,
        mission=employee["mission"],
        department=employee["department"],
        manager=employee["manager"],
        state=employee["state"],
        capabilities=list(employee["capabilities"]),
    )
    return contract

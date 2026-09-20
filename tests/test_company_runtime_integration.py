"""Focused integration tests for the deterministic Company OS lifecycle."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from ai_platform import (
    ContextKind,
    ContextManifest,
    ContextRef,
    Outcome,
    ReasoningClass,
    ReferenceViolation,
    Risk,
    SubagentPolicyViolation,
)
from ai_platform.serde import dumps
from company.runtime import (
    AttemptReport,
    ContextRequirements,
    LifecycleError,
    LifecycleState,
    ResourceUsageStore,
    TaskSpecification,
    finalise_attempt,
    load_company_config,
    plan_task,
)
from company.runtime.config import CompanyConfig
from company.runtime.__main__ import main as runtime_main
from company.runtime.tasks import HandoffArtifact
from company.validation.errors import ValidationError


ROOT = Path(__file__).resolve().parents[1]


def _config() -> CompanyConfig:
    return load_company_config(ROOT / "company")


def _context(*refs: ContextRef) -> ContextRequirements:
    return ContextRequirements(
        refs=tuple(refs),
        constraints=("Do not modify production systems.",),
        acceptance_criteria=("The focused deterministic checks pass.",),
    )


def _spec(**changes: object) -> TaskSpecification:
    values: dict[str, object] = {
        "task_id": "runtime-integration",
        "objective": "Integrate deterministic Company OS runtime primitives.",
        "required_capabilities": ("software_architecture",),
        "deterministic_execution_possible": True,
        "context": _context(
            ContextRef(
                ContextKind.MODULE_CONTRACT,
                "company/README.md",
                "Company OS dependency contract",
            )
        ),
    }
    values.update(changes)
    return TaskSpecification(**values)


def _contract(employee_id: str, config: CompanyConfig) -> dict[str, object]:
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


def test_task_classification_routing_and_selection_are_deterministic() -> None:
    config = _config()
    org = deepcopy(config.org_registry)
    for employee_id in ("zz_architect", "aa_architect"):
        org["employees"][employee_id] = {
            "department": "engineering",
            "manager": "chief_architect",
            "state": "active",
            "mission": "Provide focused software architecture.",
            "capabilities": ["software_architecture"],
        }
    config = replace(config, org_registry=org)

    first = plan_task(_spec(), config)
    second = plan_task(_spec(), config)

    assert first.classification.code is ReasoningClass.A
    assert first.classification.rule == "deterministic_software"
    assert first.routing.to_dict() == second.routing.to_dict()
    assert first.selected_employee == second.selected_employee == "aa_architect"
    assert first.state is LifecycleState.EXECUTION_PREPARED
    assert first.states == second.states


def test_capability_gap_is_an_explicit_escalation() -> None:
    plan = plan_task(
        _spec(required_capabilities=("software_architecture", "underwater_audio")),
        _config(),
    )

    assert plan.state is LifecycleState.ESCALATED
    assert plan.selected_employee is None
    assert plan.escalation.required is True
    assert "underwater_audio" in plan.missing_capabilities
    assert "no eligible employee" in plan.escalation.reason


def test_resource_class_ceiling_never_silently_downgrades() -> None:
    with pytest.raises(LifecycleError, match="exceeds allowed.*will not be silently downgraded"):
        plan_task(
            _spec(
                deterministic_execution_possible=False,
                risk=Risk.HIGH,
                reasoning_class_ceiling=ReasoningClass.C,
            ),
            _config(),
        )


def test_context_references_are_deduplicated_and_ceiling_is_enforced() -> None:
    duplicate = ContextRef(ContextKind.FILE, "company/runtime/tasks.py", "task contract")
    plan = plan_task(
        _spec(context=_context(duplicate, duplicate)),
        _config(),
    )
    assert plan.context_manifest is not None
    assert plan.context_plan is not None
    assert plan.context_manifest.keys().count(duplicate.key) == 1
    assert plan.context_plan.explicit_refs == (duplicate.key,)
    assert plan.context_plan.duplicate_count == 1
    assert set(plan.context_plan.selected_capsule_ids) == {
        "ai-platform",
        "company-knowledge-capsules",
        "company-knowledge-store",
        "company-runtime",
        "company-validation",
    }

    too_many = tuple(
        ContextRef(ContextKind.FILE, f"company/runtime/ref_{index}.py", f"ref {index}")
        for index in range(7)
    )
    with pytest.raises(LifecycleError, match="context budget"):
        plan_task(_spec(context=_context(*too_many)), _config())


def test_context_mapping_rejects_a_file_content_dump() -> None:
    with pytest.raises(ReferenceViolation, match="embedded content"):
        TaskSpecification.from_mapping(
            {
                "task_id": "content-dump",
                "objective": "Reject embedded source.",
                "required_capabilities": ["software_architecture"],
                "deterministic_execution_possible": True,
                "context": {
                    "refs": [
                        {
                            "kind": "file",
                            "ref": "def leaked():\n    return True",
                            "reason": "incorrectly pasted source",
                        }
                    ],
                    "acceptance_criteria": ["Embedded source is rejected."],
                },
            }
        )


def test_supplied_manifest_must_match_the_classified_task() -> None:
    supplied = ContextManifest(
        task_id="another-task",
        objective="Integrate deterministic Company OS runtime primitives.",
        reasoning_class=ReasoningClass.A,
        acceptance_criteria=("The focused deterministic checks pass.",),
    )
    with pytest.raises(LifecycleError, match="task_id does not match"):
        plan_task(_spec(), _config(), context_manifest=supplied)


def test_employee_contract_no_subagent_guard_is_part_of_preparation() -> None:
    config = _config()
    contract = _contract("chief_architect", config)
    contract["no_subagents"] = False

    with pytest.raises(ValidationError, match="agent_contract.no_subagents must be true"):
        plan_task(_spec(), config, employee_contract=contract)


def test_task_execution_no_subagent_guard_is_part_of_preparation() -> None:
    with pytest.raises(ValidationError, match="task.execution.subagents must be false"):
        plan_task(_spec(execution={"subagents": True}), _config())


def test_execution_policy_stops_nested_use_before_usage_persistence(tmp_path: Path) -> None:
    plan = plan_task(_spec(), _config())
    store = ResourceUsageStore(tmp_path)

    with pytest.raises(SubagentPolicyViolation, match="under policy mode"):
        finalise_attempt(
            plan,
            AttemptReport(
                outcome=Outcome.ACCEPTED,
                result="Should never persist.",
                subagents_used=1,
            ),
            store,
        )

    assert store.records() == ()


def test_required_evidence_and_malformed_handoffs_do_not_persist(tmp_path: Path) -> None:
    store = ResourceUsageStore(tmp_path)
    evidence_plan = plan_task(_spec(evidence_required=True), _config())
    with pytest.raises(LifecycleError, match="requires evidence"):
        finalise_attempt(
            evidence_plan,
            AttemptReport(outcome=Outcome.ACCEPTED, result="No evidence supplied."),
            store,
        )

    ordinary_plan = plan_task(_spec(), _config())
    with pytest.raises(ValidationError, match="result must be non-empty"):
        finalise_attempt(
            ordinary_plan,
            AttemptReport(outcome=Outcome.ACCEPTED),
            store,
        )
    assert store.records() == ()


def test_usage_history_is_append_only_reloadable_and_summarised(tmp_path: Path) -> None:
    plan = plan_task(_spec(), _config())
    store = ResourceUsageStore(tmp_path)
    assert plan.context_manifest is not None
    used = plan.context_manifest.keys()

    accepted = finalise_attempt(
        plan,
        AttemptReport(
            outcome=Outcome.ACCEPTED,
            result="Lifecycle integration accepted.",
            evidence=("focused tests passed",),
            tests=("pytest tests/test_company_runtime_integration.py",),
            context_refs_used=used,
        ),
        store,
    )
    rejected = finalise_attempt(
        plan,
        AttemptReport(
            outcome=Outcome.REJECTED,
            rejection_reason="acceptance criterion was not met",
            retries=1,
        ),
        store,
    )
    abandoned = finalise_attempt(
        plan,
        AttemptReport(
            outcome=Outcome.ABANDONED,
            notes="superseded by a later attempt",
        ),
        store,
    )

    records = store.records("runtime-integration")
    assert records == (
        accepted.usage_record,
        rejected.usage_record,
        abandoned.usage_record,
    )
    assert accepted.usage_pointer.record_ref.endswith("/000001.json")
    assert rejected.usage_pointer.record_ref.endswith("/000002.json")
    assert abandoned.usage_pointer.record_ref.endswith("/000003.json")
    assert store.load(accepted.usage_pointer) == accepted.usage_record
    assert accepted.state is LifecycleState.HANDOFF_CREATED
    assert rejected.usage_record.rejection_reason == "acceptance criterion was not met"
    assert rejected.usage_record.retries == 1
    assert rejected.usage_record.unused_context == plan.context_manifest.keys()

    stored_path = tmp_path / accepted.usage_pointer.record_ref
    assert stored_path.read_text(encoding="utf-8") == dumps(accepted.usage_record)

    summary = store.summarise("runtime-integration")
    assert summary.records == 3
    assert summary.accepted == summary.rejected == summary.abandoned == 1
    assert summary.units is None
    assert summary.units_per_accepted is None
    assert summary.passes_per_accepted == pytest.approx(3.0)
    assert summary.retries == 1


def test_handoff_contains_only_a_compact_usage_pointer(tmp_path: Path) -> None:
    result = finalise_attempt(
        plan_task(_spec(), _config()),
        AttemptReport(outcome=Outcome.ACCEPTED, result="Accepted."),
        ResourceUsageStore(tmp_path),
    )

    assert set(result.handoff.resource_usage.to_dict()) == {"record_ref", "fingerprint"}
    assert not hasattr(result.handoff.resource_usage, "context_sources")


def test_malformed_usage_pointer_makes_a_handoff_invalid() -> None:
    config = _config()
    with pytest.raises(ValidationError, match="fingerprint"):
        HandoffArtifact.from_mapping(
            {
                "task_id": "bad-handoff",
                "owner": "chief_architect",
                "objective": "Reject a malformed handoff.",
                "status": "completed",
                "result": "Invalid.",
                "evidence": [],
                "artifacts": [],
                "changed": [],
                "unchanged": [],
                "tests": [],
                "risks": [],
                "resource_usage": {
                    "record_ref": "resource_usage/bad/000001.json",
                    "fingerprint": "not-a-fingerprint",
                },
                "next_owner": "",
                "escalation": {"required": False, "reason": ""},
            },
            config.task_handoff_schema,
            known_employee_ids=set(config.org_registry["employees"]),
        )


def test_small_plan_and_usage_cli_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": "cli-plan",
                "objective": "Plan through the development CLI.",
                "required_capabilities": ["software_architecture"],
                "deterministic_execution_possible": True,
                "context": {"acceptance_criteria": ["The plan is ready."]},
            }
        ),
        encoding="utf-8",
    )

    assert runtime_main(["plan", str(task_file)]) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["state"] == "execution_prepared"
    assert planned["selected_employee"] == "chief_architect"

    assert runtime_main(["usage", str(tmp_path), "--task", "cli-plan"]) == 0
    usage = json.loads(capsys.readouterr().out)
    assert usage["records"] == []
    assert usage["summary"]["units"] is None

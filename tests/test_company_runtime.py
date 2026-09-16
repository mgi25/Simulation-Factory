from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from company.runtime.config import CompanyConfig, load_company_config
from company.runtime.routing import match_capabilities
from company.runtime.tasks import HandoffArtifact, TaskAssignment
from company.validation.bootstrap import validate_agent_contract, validate_bootstrap
from company.validation.errors import ValidationError


ROOT = Path(__file__).resolve().parents[1]


def _config_with(config: CompanyConfig, **changes: object) -> CompanyConfig:
    return replace(config, **changes)


def _valid_handoff() -> dict[str, object]:
    return {
        "task_id": "core-runtime",
        "owner": "chief_architect",
        "objective": "Validate deterministic runtime contracts.",
        "status": "completed",
        "result": "Runtime contracts validated.",
        "evidence": ["focused tests passed"],
        "artifacts": ["company/runtime"],
        "changed": ["company/runtime"],
        "unchanged": ["production systems"],
        "tests": ["pytest tests/test_company_runtime.py"],
        "risks": [],
        "resource_usage": {
            "record_ref": "resource_usage/core-runtime/000001.json",
            "fingerprint": "0123456789abcdef",
        },
        "next_owner": "studio_coo",
        "escalation": {"required": False, "reason": ""},
    }


def test_valid_bootstrap_config_passes() -> None:
    config = load_company_config(ROOT / "company")
    validate_bootstrap(config)


def test_no_subagents_false_fails() -> None:
    config = load_company_config(ROOT / "company")
    org = deepcopy(config.org_registry)
    org["global_constraints"]["no_subagents"] = False

    with pytest.raises(ValidationError, match="no_subagents.*must be true"):
        validate_bootstrap(_config_with(config, org_registry=org))


def test_invalid_manager_fails() -> None:
    config = load_company_config(ROOT / "company")
    org = deepcopy(config.org_registry)
    org["employees"]["chief_architect"]["manager"] = "missing_manager"

    with pytest.raises(ValidationError, match="references unknown employee"):
        validate_bootstrap(_config_with(config, org_registry=org))


@pytest.mark.parametrize("invalid_state", ["unreviewed", ["active"]])
def test_invalid_employee_state_fails(invalid_state: object) -> None:
    config = load_company_config(ROOT / "company")
    org = deepcopy(config.org_registry)
    org["employees"]["chief_architect"]["state"] = invalid_state

    with pytest.raises(ValidationError, match="is not a declared employment state"):
        validate_bootstrap(_config_with(config, org_registry=org))


def test_restricted_employee_cannot_receive_production_authority() -> None:
    config = load_company_config(ROOT / "company")
    org = deepcopy(config.org_registry)
    org["employees"]["chief_architect"].update(
        state="probation", production_authority=True
    )

    with pytest.raises(ValidationError, match="production_authority must be false"):
        validate_bootstrap(_config_with(config, org_registry=org))


def test_employee_contract_rejects_subagents() -> None:
    config = load_company_config(ROOT / "company")
    contract = deepcopy(config.agent_contract_schema["template"])
    contract.update(
        employee_id="sandbox_reviewer",
        mission="Review sandbox evidence.",
        department="engineering",
        manager="chief_architect",
        capabilities=["review"],
        no_subagents=False,
    )

    with pytest.raises(ValidationError, match="agent_contract.no_subagents must be true"):
        validate_agent_contract(contract, config)


def test_capability_matching_is_deterministic() -> None:
    config = load_company_config(ROOT / "company")
    org = deepcopy(config.org_registry)
    for employee_id in ("zz_simulation_specialist", "aa_simulation_specialist"):
        org["employees"][employee_id] = {
            "department": "engineering",
            "manager": "chief_architect",
            "state": "active",
            "mission": "Provide focused simulation fairness validation.",
            "capabilities": ["fairness", "simulation"],
        }
    routed_config = _config_with(config, org_registry=org)

    first = match_capabilities(["simulation", "fairness"], routed_config)
    second = match_capabilities(["fairness", "simulation"], routed_config)

    assert first.to_dict() == second.to_dict()
    assert first.eligible_employee_ids == (
        "aa_simulation_specialist",
        "zz_simulation_specialist",
        "simulation_physics_engineer",
    )


def test_missing_capabilities_are_reported() -> None:
    config = load_company_config(ROOT / "company")
    result = match_capabilities(["simulation", "fairness", "underwater_audio"], config)
    match = next(
        item for item in result.matches if item.employee_id == "simulation_physics_engineer"
    )

    assert match.matched_capabilities == ("fairness", "simulation")
    assert match.missing_capabilities == ("underwater_audio",)
    assert not match.eligible
    assert "underwater_audio" in match.eligibility_reason


def test_invalid_handoff_fails_early() -> None:
    config = load_company_config(ROOT / "company")
    handoff = _valid_handoff()
    handoff["escalation"] = {"required": True, "reason": ""}

    with pytest.raises(ValidationError, match="reason is required"):
        HandoffArtifact.from_mapping(handoff, config.task_handoff_schema)


def test_valid_handoff_builds_typed_artifact() -> None:
    config = load_company_config(ROOT / "company")
    artifact = HandoffArtifact.from_mapping(
        _valid_handoff(),
        config.task_handoff_schema,
        known_employee_ids=set(config.org_registry["employees"]),
    )

    assert artifact.task_id == "core-runtime"
    assert artifact.status.value == "completed"
    assert artifact.resource_usage.fingerprint == "0123456789abcdef"


@pytest.mark.parametrize(
    "execution",
    [
        {"subagents": True},
        {"child_workers": 1},
        {"nested_delegation": True},
        {"autonomous_worker_spawning": True},
    ],
)
def test_task_execution_rejects_nested_workers(execution: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="must be false in Bootstrap Mode"):
        TaskAssignment.from_mapping(
            {
                "task_id": "no-nesting",
                "owner": "chief_architect",
                "objective": "Execute directly.",
                "status": "assigned",
                "required_capabilities": ["software_architecture"],
                "execution": execution,
            }
        )


def test_production_sources_do_not_import_company_runtime() -> None:
    production_directories = (
        "race",
        "engine",
        "modes",
        "powers",
        "godot",
        "marble3d",
        "sloped",
    )
    violations: list[str] = []
    for directory in production_directories:
        for source in sorted((ROOT / directory).rglob("*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                if any(module == "company" or module.startswith("company.") for module in modules):
                    violations.append(str(source.relative_to(ROOT)))

    assert violations == []

from __future__ import annotations

import ast
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from company.config_types import CompanyConfig as ContractCompanyConfig
from company.runtime.config import CompanyConfig, load_company_config
from company.runtime.routing import match_capabilities
from company.runtime.tasks import HandoffArtifact, TaskAssignment
from company.validation.bootstrap import validate_agent_contract, validate_bootstrap
from company.validation.errors import ValidationError


ROOT = Path(__file__).resolve().parents[1]


def test_company_config_has_one_neutral_definition() -> None:
    assert CompanyConfig is ContractCompanyConfig


def test_validation_does_not_import_runtime_implementation_modules() -> None:
    violations: list[str] = []
    for source in sorted((ROOT / "company/validation").rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports_runtime = any(
                    alias.name == "company.runtime"
                    or alias.name.startswith("company.runtime.")
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports_runtime = (
                    module == "company.runtime"
                    or module.startswith("company.runtime.")
                    or (
                        module == "company"
                        and any(
                            alias.name == "runtime"
                            or alias.name.startswith("runtime.")
                            for alias in node.names
                        )
                    )
                    or (
                        node.level >= 2
                        and (
                            module == "runtime" or module.startswith("runtime.")
                        )
                    )
                )
            else:
                continue
            if imports_runtime:
                violations.append(f"{source.relative_to(ROOT)}:{node.lineno}")

    assert violations == []


@pytest.mark.parametrize(
    "first,second",
    [
        ("company.runtime", "company.validation"),
        ("company.validation", "company.runtime"),
    ],
)
def test_runtime_and_validation_import_order_is_independent(
    first: str, second: str
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib; "
                f"importlib.import_module({first!r}); "
                f"importlib.import_module({second!r})"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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


# --- The packet command's authority line, with and without an outbox ---------
#
# `packet --state-dir` persists an authority snapshot and prints its fingerprint
# and source. Without one, nothing is persisted - but the packet can still carry
# a writable path, and an operator handed that packet needs the same two fields
# to say what grant is behind it. The snapshot printed there is the one attempt 1
# would be prepared under, and `record_ref` is null because it was not recorded.


def _echo_task_file(tmp_path: Path, task_id: str) -> Path:
    import json

    task_file = tmp_path / f"{task_id}.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "objective": "Show the authority behind a packet built without an outbox.",
                "required_capabilities": [
                    "software_implementation",
                    "test_engineering",
                ],
                "deterministic_execution_possible": False,
                "context": {
                    "refs": [
                        {
                            "kind": "file",
                            "ref": "company/runtime/packets.py",
                            "reason": "initial packet boundary",
                        }
                    ],
                    "constraints": ["Do not modify production systems."],
                    "acceptance_criteria": ["The authority line is printed."],
                },
            }
        ),
        encoding="utf-8",
    )
    return task_file


def test_a_read_only_packet_built_without_an_outbox_still_names_its_authority(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from company.runtime.__main__ import main as runtime_main

    task_file = _echo_task_file(tmp_path, "authority-echo-readonly")

    assert (
        runtime_main(["packet", str(task_file), "--branch", "authority-echo"]) == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["authority"]["record_ref"] is None
    assert payload["authority"]["source"] == "canonical_contract"
    assert len(payload["authority"]["fingerprint"]) == 16
    assert not list(tmp_path.glob("**/execution"))


def test_a_write_scoped_packet_prints_the_same_authority_with_or_without_an_outbox(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    from company.runtime.__main__ import main as runtime_main

    task_file = _echo_task_file(tmp_path, "authority-echo-granted")
    override = tmp_path / "authority.json"
    override.write_text(
        json.dumps({"may_write": ["tests/test_company_runtime.py"]}), encoding="utf-8"
    )
    argv = [
        "packet",
        str(task_file),
        "--branch",
        "authority-echo",
        "--allow",
        "tests/test_company_runtime.py",
        "--authority-override-file",
        str(override),
    ]

    assert runtime_main(argv) == 0
    unpersisted = json.loads(capsys.readouterr().out)

    state = tmp_path / "state"
    assert runtime_main([*argv, "--state-dir", str(state)]) == 0
    persisted = json.loads(capsys.readouterr().out)

    # The same grant, named the same way. Only where it was written differs.
    assert unpersisted["packet"] == persisted["packet"]
    assert unpersisted["fingerprint"] == persisted["fingerprint"]
    assert (
        unpersisted["authority"]["fingerprint"]
        == persisted["authority"]["fingerprint"]
    )
    assert unpersisted["authority"]["source"] == "temporary_task_override"
    assert persisted["authority"]["source"] == "temporary_task_override"
    assert unpersisted["authority"]["record_ref"] is None
    assert persisted["authority"]["record_ref"].startswith("execution/authorities/")
    # The outbox-less run added no keys of its own and dropped none.
    assert set(unpersisted) == {"packet", "fingerprint", "size_chars", "authority"}
    assert set(persisted) == set(unpersisted) | {"persisted", "transport"}

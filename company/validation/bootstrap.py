"""Validation of Company OS bootstrap contracts and organizational invariants."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from company.config_types import CompanyConfig
from .errors import ValidationError
from .no_subagents import collect_no_subagent_violations


BOOTSTRAP_DEPARTMENTS = frozenset(
    {
        "ai_platform",
        "creative",
        "data",
        "engineering",
        "executive",
        "intelligence",
        "people",
        "production",
    }
)
VALID_EMPLOYMENT_STATES = frozenset(
    {"candidate", "shadow", "probation", "active", "dormant", "archived"}
)
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*")
_RESTRICTED_STATES = frozenset({"candidate", "shadow", "probation"})
_PRODUCTION_ACTIONS = frozenset(
    {
        "approved_code_write",
        "approved_operational_actions",
        "approved_org_or_architecture_change",
        "production_write",
    }
)
_CRITICAL_CEO_ACTIONS = frozenset(
    {"change_company_mission", "amend_constitution", "change_no_subagents_policy"}
)


def validate_bootstrap(config: CompanyConfig) -> None:
    """Validate the complete v1 bootstrap configuration, collecting useful errors."""

    issues: list[str] = []
    org = config.org_registry
    permissions = config.permissions

    _expect_version_and_mode(org, "org_registry", issues)
    _expect_version_and_mode(permissions, "permissions", issues)
    if org.get("human_ceo") is not True:
        issues.append("org_registry.human_ceo must be true")

    constraints = _mapping(org.get("global_constraints"), "org_registry.global_constraints", issues)
    _expect_exact_bool(constraints, "no_subagents", True, "org_registry.global_constraints", issues)
    _expect_exact_bool(
        constraints, "nested_agent_spawning", False, "org_registry.global_constraints", issues
    )
    _expect_exact_bool(constraints, "always_on_agents", False, "org_registry.global_constraints", issues)

    defaults = _mapping(
        permissions.get("bootstrap_defaults"), "permissions.bootstrap_defaults", issues
    )
    _expect_exact_bool(defaults, "no_subagents", True, "permissions.bootstrap_defaults", issues)

    declared_states = _string_list(
        org.get("employment_states"), "org_registry.employment_states", issues, nonempty=True
    )
    state_set = set(declared_states)
    unsupported_states = state_set - VALID_EMPLOYMENT_STATES
    if unsupported_states:
        issues.append(
            "org_registry.employment_states contains unsupported states: "
            + ", ".join(sorted(unsupported_states))
        )
    if len(declared_states) != len(state_set):
        issues.append("org_registry.employment_states must not contain duplicates")
    default_state = org.get("default_employee_state")
    if not isinstance(default_state, str) or default_state not in state_set:
        issues.append("org_registry.default_employee_state must be a declared employment state")

    employees = _mapping(org.get("employees"), "org_registry.employees", issues)
    if not employees:
        issues.append("org_registry.employees must define at least one employee")
    _validate_employees(employees, state_set, defaults, bool(org.get("human_ceo")), issues)
    _validate_permissions(permissions, defaults, issues)
    _validate_schema(config.agent_contract_schema, "agent_contract.schema", issues)
    _validate_schema(config.task_handoff_schema, "task_handoff.schema", issues)

    issues.extend(
        collect_no_subagent_violations(constraints, path="org_registry.global_constraints")
    )
    issues.extend(
        collect_no_subagent_violations(defaults, path="permissions.bootstrap_defaults")
    )
    agent_template = config.agent_contract_schema.get("template")
    if isinstance(agent_template, Mapping):
        issues.extend(
            collect_no_subagent_violations(agent_template, path="agent_contract.schema.template")
        )

    if issues:
        raise ValidationError(issues)


def validate_agent_contract(
    contract: Mapping[str, Any], config: CompanyConfig
) -> None:
    """Validate one employee contract against the canonical agent schema."""

    issues: list[str] = []
    required = _string_list(
        config.agent_contract_schema.get("required_fields"),
        "agent_contract.schema.required_fields",
        issues,
        nonempty=True,
    )
    for field in required:
        if field not in contract:
            issues.append(f"agent_contract.{field} is required")
    for field in ("employee_id", "mission", "department", "manager"):
        if field in contract and not _nonempty_string(contract[field]):
            issues.append(f"agent_contract.{field} must be a non-empty string")
    department = contract.get("department")
    if not isinstance(department, str) or department not in BOOTSTRAP_DEPARTMENTS:
        issues.append("agent_contract.department is not a Bootstrap v1 department")
    state = contract.get("state", "candidate")
    declared_states = config.org_registry.get("employment_states", [])
    if not isinstance(state, str) or state not in declared_states:
        issues.append(f"agent_contract.state {state!r} is not declared")
    _string_list(contract.get("capabilities"), "agent_contract.capabilities", issues)
    for field in ("input_contract", "output_contract", "may_read", "may_write"):
        _string_list(contract.get(field), f"agent_contract.{field}", issues)
    issues.extend(collect_no_subagent_violations(contract, path="agent_contract"))
    _validate_restricted_authority("agent_contract", contract, state, _state_caps(config.permissions), issues)
    if issues:
        raise ValidationError(issues)


def _expect_version_and_mode(data: Mapping[str, Any], path: str, issues: list[str]) -> None:
    if data.get("version") != 1:
        issues.append(f"{path}.version must be 1")
    if data.get("mode") != "bootstrap":
        issues.append(f"{path}.mode must be 'bootstrap'")


def _validate_employees(
    employees: Mapping[str, Any],
    declared_states: set[str],
    defaults: Mapping[str, Any],
    human_ceo: bool,
    issues: list[str],
) -> None:
    caps = _state_caps_from_defaults(defaults, issues)
    valid_ids = {employee_id for employee_id in employees if isinstance(employee_id, str)}
    managers: dict[str, str] = {}
    for employee_id in sorted(employees, key=str):
        path = f"org_registry.employees.{employee_id}"
        if not isinstance(employee_id, str) or not _IDENTIFIER.fullmatch(employee_id):
            issues.append(f"{path}: employee ID must be a lowercase snake_case identifier")
        employee = _mapping(employees[employee_id], path, issues)
        department = employee.get("department")
        if not isinstance(department, str) or department not in BOOTSTRAP_DEPARTMENTS:
            issues.append(
                f"{path}.department must be one of: {', '.join(sorted(BOOTSTRAP_DEPARTMENTS))}"
            )
        mission = employee.get("mission")
        if not _nonempty_string(mission):
            issues.append(f"{path}.mission must be a non-empty string")
        capabilities = _string_list(
            employee.get("capabilities"), f"{path}.capabilities", issues, nonempty=True
        )
        if len(capabilities) != len(set(capabilities)):
            issues.append(f"{path}.capabilities must not contain duplicates")
        state = employee.get("state")
        if not isinstance(state, str) or state not in declared_states:
            issues.append(f"{path}.state {state!r} is not a declared employment state")
        manager = employee.get("manager")
        if not _nonempty_string(manager):
            issues.append(f"{path}.manager must be a non-empty string")
        elif manager == "ceo":
            if not human_ceo:
                issues.append(f"{path}.manager references ceo but human_ceo is not enabled")
            managers[str(employee_id)] = manager
        elif not isinstance(manager, str) or manager not in valid_ids:
            issues.append(f"{path}.manager references unknown employee {manager!r}")
        else:
            managers[str(employee_id)] = manager
        _validate_restricted_authority(path, employee, state, caps, issues)
        issues.extend(collect_no_subagent_violations(employee, path=path))
    _validate_manager_chains(managers, issues)


def _validate_manager_chains(managers: Mapping[str, str], issues: list[str]) -> None:
    for employee_id in sorted(managers):
        chain: list[str] = []
        current = employee_id
        while current != "ceo" and current in managers:
            if current in chain:
                cycle = chain[chain.index(current) :] + [current]
                issues.append("manager cycle detected: " + " -> ".join(cycle))
                break
            chain.append(current)
            current = managers[current]


def _validate_permissions(
    permissions: Mapping[str, Any], defaults: Mapping[str, Any], issues: list[str]
) -> None:
    levels = _mapping(permissions.get("autonomy_levels"), "permissions.autonomy_levels", issues)
    for level in range(6):
        entry = levels.get(str(level))
        path = f"permissions.autonomy_levels.{level}"
        entry_map = _mapping(entry, path, issues)
        if not _nonempty_string(entry_map.get("name")):
            issues.append(f"{path}.name must be a non-empty string")
        _string_list(entry_map.get("allows"), f"{path}.allows", issues, nonempty=True)

    caps = _state_caps_from_defaults(defaults, issues)
    if caps.get("candidate") != 0:
        issues.append("permissions.bootstrap_defaults.candidate_level must be 0")
    if caps.get("shadow") != 1:
        issues.append("permissions.bootstrap_defaults.shadow_level must be 1")
    if caps.get("probation") != 2:
        issues.append("permissions.bootstrap_defaults.probation_max_level must be 2")
    new_level = defaults.get("new_employee_level")
    if not _integer_not_bool(new_level) or not 0 <= new_level <= 2:
        issues.append("permissions.bootstrap_defaults.new_employee_level must be an integer from 0 to 2")
    _string_list(
        defaults.get("production_write_requires"),
        "permissions.bootstrap_defaults.production_write_requires",
        issues,
        nonempty=True,
    )

    reserved = _string_list(
        permissions.get("ceo_reserved"), "permissions.ceo_reserved", issues, nonempty=True
    )
    if len(reserved) != len(set(reserved)):
        issues.append("permissions.ceo_reserved must not contain duplicates")
    missing = _CRITICAL_CEO_ACTIONS - set(reserved)
    if missing:
        issues.append("permissions.ceo_reserved is missing: " + ", ".join(sorted(missing)))


def _validate_schema(schema: Mapping[str, Any], path: str, issues: list[str]) -> None:
    if schema.get("version") != 1:
        issues.append(f"{path}.version must be 1")
    required = _string_list(schema.get("required_fields"), f"{path}.required_fields", issues, nonempty=True)
    if len(required) != len(set(required)):
        issues.append(f"{path}.required_fields must not contain duplicates")
    template = _mapping(schema.get("template"), f"{path}.template", issues)
    for field in required:
        if field not in template:
            issues.append(f"{path}.template is missing required field {field!r}")


def _validate_restricted_authority(
    path: str,
    employee: Mapping[str, Any],
    state: Any,
    caps: Mapping[str, int],
    issues: list[str],
) -> None:
    if not isinstance(state, str) or state not in _RESTRICTED_STATES:
        return
    autonomy_level = employee.get("autonomy_level")
    if autonomy_level is not None:
        if not _integer_not_bool(autonomy_level):
            issues.append(f"{path}.autonomy_level must be an integer")
        elif autonomy_level > caps.get(str(state), -1):
            issues.append(
                f"{path}.autonomy_level {autonomy_level} exceeds the {state} cap "
                f"of {caps.get(str(state), -1)}"
            )
    for flag in ("production_authority", "production_write", "can_modify_production"):
        if flag in employee and employee[flag] is not False:
            issues.append(f"{path}.{flag} must be false for {state} employees")
    for field in ("permissions", "may_write", "decisions_allowed", "actions"):
        value = employee.get(field)
        if isinstance(value, list):
            forbidden = _PRODUCTION_ACTIONS.intersection(item for item in value if isinstance(item, str))
            if forbidden:
                issues.append(
                    f"{path}.{field} grants production authority to a {state} employee: "
                    + ", ".join(sorted(forbidden))
                )


def _state_caps(permissions: Mapping[str, Any]) -> dict[str, int]:
    defaults = permissions.get("bootstrap_defaults")
    if not isinstance(defaults, Mapping):
        return {}
    result: dict[str, int] = {}
    for state, field in (
        ("candidate", "candidate_level"),
        ("shadow", "shadow_level"),
        ("probation", "probation_max_level"),
    ):
        value = defaults.get(field)
        if _integer_not_bool(value):
            result[state] = value
    return result


def _state_caps_from_defaults(
    defaults: Mapping[str, Any], issues: list[str]
) -> dict[str, int]:
    result: dict[str, int] = {}
    for state, field in (
        ("candidate", "candidate_level"),
        ("shadow", "shadow_level"),
        ("probation", "probation_max_level"),
    ):
        value = defaults.get(field)
        if not _integer_not_bool(value):
            issues.append(f"permissions.bootstrap_defaults.{field} must be an integer")
        else:
            result[state] = value
    return result


def _mapping(value: Any, path: str, issues: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        issues.append(f"{path} must be a mapping")
        return {}
    return value


def _string_list(
    value: Any, path: str, issues: list[str], *, nonempty: bool = False
) -> list[str]:
    if not isinstance(value, list) or any(not _nonempty_string(item) for item in value):
        issues.append(f"{path} must be a list of non-empty strings")
        return []
    if nonempty and not value:
        issues.append(f"{path} must not be empty")
    return value


def _expect_exact_bool(
    data: Mapping[str, Any], key: str, expected: bool, path: str, issues: list[str]
) -> None:
    if data.get(key) is not expected:
        issues.append(f"{path}.{key} must be {str(expected).lower()}")


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _integer_not_bool(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)

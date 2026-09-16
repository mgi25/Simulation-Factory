"""Every cross-record invariant, checked in one pass and reported together.

The record classes in this package each refuse what they can see on their own.
What none of them can see is the other records: a `RoleSpecification` cannot
know whether its manager exists, an `EmploymentRecord` cannot know whether the
employee is in the org registry, and a capability's uniqueness is a property of
the whole registry.

So this module takes everything and returns *every* problem, sorted, in the
style `company/validation/bootstrap.py` established: collecting the issues and
raising once means a session fixing an organization learns the whole shape of
the problem instead of the first line of it.

The eleven checks are section 16 of the brief, one function each. Three of them
are authority checks, and those are the ones worth reading twice:

    _candidate_authority   a candidate above autonomy level 0, or holding a
                           production action
    _shadow_writes         a shadow assignment with any write scope at all
    _role_no_subagents     a proposed role with `no_subagents` anything but True

Each is unreachable through the normal constructors - the dataclasses refuse
first - which makes them the check for records that arrived another way: an
older file, a hand-edited JSON, another tool.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .capabilities import CapabilityRegistry, Criticality
from .employment import (
    PRODUCTION_WRITE_ACTIONS,
    EmploymentRecord,
    EmploymentState,
    history_violations,
    state_authority_cap,
)
from .errors import WorkforceIntegrityError
from .evaluation import CandidateEvaluation
from .roles import RoleSpecification
from .shadow import ShadowAssignment


def check_integrity(
    registry: CapabilityRegistry,
    *,
    permissions: Mapping[str, Any] | None = None,
    role_specifications: Iterable[RoleSpecification] = (),
    employment_records: Iterable[EmploymentRecord] = (),
    evaluations: Iterable[CandidateEvaluation] = (),
    shadow_assignments: Iterable[ShadowAssignment] = (),
) -> tuple[str, ...]:
    """Return every integrity problem found, sorted. Empty means clean."""
    roles = tuple(role_specifications)
    records = tuple(employment_records)
    evals = tuple(evaluations)
    shadows = tuple(shadow_assignments)
    permission_map = dict(permissions) if permissions else {}

    issues: list[str] = []
    issues.extend(_unknown_employee_capabilities(registry))
    issues.extend(_duplicate_capability_ids(registry))
    issues.extend(_uncovered_critical_capabilities(registry))
    issues.extend(_capability_providers_in_registry(registry, roles))
    issues.extend(_role_managers(registry, roles))
    issues.extend(_manager_cycles(registry, roles))
    issues.extend(_role_no_subagents(roles))
    issues.extend(_role_authority(roles, permission_map))
    issues.extend(_shadow_writes(shadows))
    issues.extend(_shadow_subjects(registry, roles, records, shadows))
    issues.extend(_evaluation_subjects(registry, roles, records, evals))
    issues.extend(_lifecycle_jumps(records))
    issues.extend(_registry_state_alignment(registry, records))
    issues.extend(_employment_authority(records, permission_map))
    return tuple(sorted(dict.fromkeys(issues)))


def assert_integrity(registry: CapabilityRegistry, **kwargs: Any) -> None:
    issues = check_integrity(registry, **kwargs)
    if issues:
        raise WorkforceIntegrityError(issues)


# -- capability model -----------------------------------------------------


def _unknown_employee_capabilities(registry: CapabilityRegistry) -> list[str]:
    return [
        f"org_registry.employees.{employee_id}: capability {capability_id!r} is not defined "
        "in the capability registry"
        for employee_id, capability_id in registry.unregistered_employee_capabilities()
    ]


def _duplicate_capability_ids(registry: CapabilityRegistry) -> list[str]:
    """Duplicates cannot survive `CapabilityGraph`, so this reports a raw list.

    Kept because integrity runs over data that may not have come through the
    graph - a JSON file someone is about to load, for instance.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for capability in registry.graph.capabilities:
        if capability.capability_id in seen:
            duplicates.add(capability.capability_id)
        seen.add(capability.capability_id)
    return [f"duplicate capability id {capability_id!r}" for capability_id in sorted(duplicates)]


def _uncovered_critical_capabilities(registry: CapabilityRegistry) -> list[str]:
    return [
        f"capability {resolved.capability_id!r} is core and has no provider in the org registry"
        for resolved in registry.resolved()
        if resolved.capability.criticality is Criticality.CORE and not resolved.provided_by
    ]


def _capability_providers_in_registry(
    registry: CapabilityRegistry, roles: tuple[RoleSpecification, ...]
) -> list[str]:
    """A proposed role's capabilities must exist before the role can claim them."""
    return [
        f"role {role.role_id}: required capability {capability_id!r} is not defined in the "
        "capability registry"
        for role in roles
        for capability_id in role.required_capabilities
        if capability_id not in registry.graph
    ]


# -- org shape ------------------------------------------------------------


def _role_managers(
    registry: CapabilityRegistry, roles: tuple[RoleSpecification, ...]
) -> list[str]:
    known = set(registry.employee_ids) | {"ceo"} | {role.role_id for role in roles}
    return [
        f"role {role.role_id}: manager {role.manager!r} is neither an employee, another "
        "proposed role, nor the CEO"
        for role in roles
        if role.manager not in known
    ]


def _manager_cycles(
    registry: CapabilityRegistry, roles: tuple[RoleSpecification, ...]
) -> list[str]:
    """Follow every management chain to the CEO, or to the loop it is stuck in."""
    managers: dict[str, str] = {
        employee_id: registry.employee_manager(employee_id)
        for employee_id in registry.employee_ids
    }
    for role in roles:
        managers[role.role_id] = role.manager
    out: list[str] = []
    for start in sorted(managers):
        chain: list[str] = []
        current = start
        while current in managers and current != "ceo":
            if current in chain:
                cycle = chain[chain.index(current) :] + [current]
                out.append("proposed manager cycle detected: " + " -> ".join(cycle))
                break
            chain.append(current)
            current = managers[current]
    return out


# -- authority ------------------------------------------------------------


def _role_no_subagents(roles: tuple[RoleSpecification, ...]) -> list[str]:
    return [
        f"role {role.role_id}: no_subagents is {role.no_subagents!r}; constitution rule 2 "
        "requires exactly true and amending it needs CEO approval"
        for role in roles
        if role.no_subagents is not True
    ]


def _role_authority(
    roles: tuple[RoleSpecification, ...], permissions: Mapping[str, Any]
) -> list[str]:
    out: list[str] = []
    for role in roles:
        if not role.is_restricted:
            continue
        requested = PRODUCTION_WRITE_ACTIONS.intersection(
            tuple(role.proposed_may_write) + tuple(role.tools)
        )
        if requested:
            out.append(
                f"role {role.role_id}: a {role.state} role requests production authority "
                + ", ".join(sorted(requested))
            )
        contract = role.to_contract(permissions=dict(permissions) or None)
        if contract.get("may_write"):
            out.append(
                f"role {role.role_id}: a {role.state} contract emitted a non-empty may_write"
            )
        level = contract.get("autonomy_level")
        if permissions and isinstance(level, int):
            state = EmploymentState(role.state)
            cap = state_authority_cap(state, dict(permissions))
            if level > cap:
                out.append(
                    f"role {role.role_id}: autonomy level {level} exceeds the {role.state} "
                    f"cap of {cap}"
                )
    return out


def _shadow_writes(shadows: tuple[ShadowAssignment, ...]) -> list[str]:
    out: list[str] = []
    for assignment in shadows:
        if assignment.may_write:
            out.append(
                f"shadow {assignment.assignment_id}: holds a write scope "
                + ", ".join(assignment.may_write)
                + "; a shadow is compared, not merged"
            )
        if assignment.production_write is not False:
            out.append(
                f"shadow {assignment.assignment_id}: production_write is "
                f"{assignment.production_write!r}, must be False"
            )
    return out


def _employment_authority(
    records: tuple[EmploymentRecord, ...], permissions: Mapping[str, Any]
) -> list[str]:
    """A restricted employee that reached a state its cap forbids.

    The cap itself is read from `permissions.yaml`; with no permissions supplied
    the check is skipped rather than guessed, and the caller is expected to
    supply them in the pass that matters.
    """
    if not permissions:
        return []
    out: list[str] = []
    for record in records:
        if record.state is not EmploymentState.CANDIDATE:
            continue
        if state_authority_cap(EmploymentState.CANDIDATE, dict(permissions)) != 0:
            out.append(
                "permissions.bootstrap_defaults.candidate_level is not 0; a candidate would "
                "receive authority before any evaluation ran"
            )
    return out


# -- lifecycle ------------------------------------------------------------


def _lifecycle_jumps(records: tuple[EmploymentRecord, ...]) -> list[str]:
    return [issue for record in records for issue in history_violations(record)]


def _registry_state_alignment(
    registry: CapabilityRegistry, records: tuple[EmploymentRecord, ...]
) -> list[str]:
    """Every non-rejected lifecycle state must exist in the org registry's vocabulary.

    This is the check that keeps `REJECTED` honest: it is the one state with no
    registry equivalent, and if any other state loses its equivalent the two
    vocabularies have drifted and this says so.
    """
    out: list[str] = []
    for state in EmploymentState:
        if state is EmploymentState.REJECTED:
            if state.registry_state is not None:
                out.append("EmploymentState.REJECTED must not map to an org registry state")
            continue
        if state.registry_state != state.value:
            out.append(f"employment state {state.value!r} has no org registry equivalent")
    known = set(registry.employee_ids)
    for record in records:
        if record.state is EmploymentState.REJECTED and record.employee_id in known:
            out.append(
                f"{record.employee_id}: rejected, but present in org_registry.yaml. A rejected "
                "candidate never became an employee"
            )
    return out


def _shadow_subjects(
    registry: CapabilityRegistry,
    roles: tuple[RoleSpecification, ...],
    records: tuple[EmploymentRecord, ...],
    shadows: tuple[ShadowAssignment, ...],
) -> list[str]:
    known = _known_subjects(registry, roles, records)
    out: list[str] = []
    for assignment in shadows:
        if assignment.candidate_id not in known:
            out.append(
                f"shadow {assignment.assignment_id}: unknown candidate "
                f"{assignment.candidate_id!r}"
            )
        if assignment.baseline_employee_id not in set(registry.employee_ids):
            out.append(
                f"shadow {assignment.assignment_id}: baseline "
                f"{assignment.baseline_employee_id!r} is not in the org registry"
            )
        for capability_id in assignment.capabilities:
            if capability_id not in registry.graph:
                out.append(
                    f"shadow {assignment.assignment_id}: unknown capability {capability_id!r}"
                )
    return out


def _evaluation_subjects(
    registry: CapabilityRegistry,
    roles: tuple[RoleSpecification, ...],
    records: tuple[EmploymentRecord, ...],
    evaluations: tuple[CandidateEvaluation, ...],
) -> list[str]:
    known = _known_subjects(registry, roles, records)
    known_roles = {role.role_id for role in roles}
    out: list[str] = []
    for evaluation in evaluations:
        if evaluation.candidate_id not in known:
            out.append(
                f"evaluation {evaluation.evaluation_id}: unknown employee "
                f"{evaluation.candidate_id!r}"
            )
        if roles and evaluation.role_specification_id not in known_roles:
            out.append(
                f"evaluation {evaluation.evaluation_id}: role specification "
                f"{evaluation.role_specification_id!r} was not supplied"
            )
        for case in evaluation.cases:
            if case.capability_id and case.capability_id not in registry.graph:
                out.append(
                    f"evaluation {evaluation.evaluation_id}: case {case.test_id} names unknown "
                    f"capability {case.capability_id!r}"
                )
    return out


def _known_subjects(
    registry: CapabilityRegistry,
    roles: tuple[RoleSpecification, ...],
    records: tuple[EmploymentRecord, ...],
) -> set[str]:
    return (
        set(registry.employee_ids)
        | {role.role_id for role in roles}
        | {record.employee_id for record in records}
    )

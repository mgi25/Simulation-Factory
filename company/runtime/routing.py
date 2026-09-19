"""Deterministic, explainable employee capability routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import CompanyConfig


_ROUTABLE_STATES = frozenset({"active", "dormant"})
_STATE_ORDER = {"active": 0, "dormant": 1, "probation": 2, "shadow": 3, "candidate": 4, "archived": 5}


@dataclass(frozen=True)
class EmployeeMatch:
    employee_id: str
    state: str
    matched_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    eligible: bool
    eligibility_reason: str
    extra_capability_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "state": self.state,
            "matched_capabilities": list(self.matched_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "eligible": self.eligible,
            "eligibility_reason": self.eligibility_reason,
        }


@dataclass(frozen=True)
class RoutingResult:
    required_capabilities: tuple[str, ...]
    matches: tuple[EmployeeMatch, ...]

    @property
    def eligible_employee_ids(self) -> tuple[str, ...]:
        return tuple(match.employee_id for match in self.matches if match.eligible)

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_capabilities": list(self.required_capabilities),
            "eligible_employee_ids": list(self.eligible_employee_ids),
            "matches": [match.to_dict() for match in self.matches],
        }


def match_capabilities(
    required_capabilities: list[str] | tuple[str, ...], config: CompanyConfig
) -> RoutingResult:
    """Rank exact-capability employees and explain every employee's result.

    Active employees rank before dormant employees. Equally eligible employees
    rank by specialization (fewest unrelated capabilities), then employee ID.
    """

    if not required_capabilities:
        raise ValueError("at least one required capability is needed")
    if any(not isinstance(item, str) or not item.strip() for item in required_capabilities):
        raise ValueError("required capabilities must be non-empty strings")
    required = tuple(sorted({item.strip().casefold() for item in required_capabilities}))
    employees = config.org_registry.get("employees", {})
    matches: list[EmployeeMatch] = []
    for employee_id in sorted(employees):
        employee = employees[employee_id]
        raw_capabilities = employee.get("capabilities", [])
        capabilities = {
            capability.casefold()
            for capability in raw_capabilities
            if isinstance(capability, str)
        }
        matched = tuple(capability for capability in required if capability in capabilities)
        missing = tuple(capability for capability in required if capability not in capabilities)
        state = str(employee.get("state", ""))
        if missing:
            eligible = False
            reason = "missing required capabilities: " + ", ".join(missing)
        elif state not in _ROUTABLE_STATES:
            eligible = False
            reason = f"employee state {state!r} is not routable in Bootstrap Mode"
        else:
            eligible = True
            reason = f"all required capabilities matched; {state} employees are routable"
        matches.append(
            EmployeeMatch(
                employee_id=employee_id,
                state=state,
                matched_capabilities=matched,
                missing_capabilities=missing,
                eligible=eligible,
                eligibility_reason=reason,
                extra_capability_count=len(capabilities - set(required)),
            )
        )
    matches.sort(key=_match_sort_key)
    return RoutingResult(required_capabilities=required, matches=tuple(matches))


def _match_sort_key(match: EmployeeMatch) -> tuple[int, int, int, int, int, str]:
    return (
        0 if match.eligible else 1,
        -len(match.matched_capabilities),
        len(match.missing_capabilities),
        _STATE_ORDER.get(match.state, 99),
        match.extra_capability_count,
        match.employee_id,
    )

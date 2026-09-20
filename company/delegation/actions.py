"""The closed set of action types, and which of them the CEO has reserved.

## Why the set is closed

An authority model whose action vocabulary is open has no fail-closed state: an
action nobody classified would arrive, match no grant, and be handled by
whatever the default is. So `ActionType` is an enum, an unrecognised name is
refused at construction, and the one member that exists for the unknown case —
`UNCLASSIFIED` — is permanently CEO-reserved. A caller that does not know what
it is asking for is asking the CEO.

## Why the reserved list is read and not restated

`company/permissions.yaml` already names the CEO-reserved decisions, and
`company/integration/contracts.py` fails the gate if that list shrinks past the
eight it depends on. Restating those names here would create a second source of
truth for the one list the whole safety argument rests on (constitution rule
15), and the two copies would drift in exactly the direction that matters: this
file could keep reserving something the canonical file had released, or release
something it still reserves.

`reserved_action_types` therefore takes the loaded permissions mapping and
returns the action types whose reserved name appears in it. An action whose
reserved name is missing from `permissions.yaml` is reported by
`reservation_drift` rather than silently becoming delegable — the same
two-directional comparison the gate does.

## Why some actions are reserved with no name in permissions.yaml

Four action types — changing the delegation policy, expanding authority,
changing a governance policy, and `UNCLASSIFIED` — are reserved by this package
itself and appear in `RESERVED_HERE`. They are the actions that would let the
delegation model rewrite its own limits, and the constitution amendment clause
already covers the class ("changing the production permission model ... requires
explicit CEO approval") without naming them. They are reserved
unconditionally, so a `permissions.yaml` that never mentions them still cannot
release them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .errors import DelegationError


class ActionType(str, Enum):
    """Every action the delegation model can reason about. Closed on purpose."""

    # -- engineering -------------------------------------------------------
    APPROVE_WORK_ORDER = "approve_work_order"
    APPROVE_CODE_CHANGE = "approve_code_change"
    APPROVE_TEST_PROGRESSION = "approve_test_progression"
    REQUEST_BOUNDED_CORRECTION = "request_bounded_correction"
    APPROVE_REVIEW_OUTCOME = "approve_review_outcome"
    STOP_WORK_ON_INVALID_PREMISE = "stop_work_on_invalid_premise"
    APPROVE_INTEGRATION_MERGE = "approve_integration_merge"
    APPROVE_ARCHITECTURE_REDESIGN = "approve_architecture_redesign"
    APPROVE_NEW_DEPENDENCY = "approve_new_dependency"
    APPROVE_DEPLOYMENT = "approve_deployment"
    CHANGE_PRIMARY_ENGINE = "change_primary_engine"

    # -- money -------------------------------------------------------------
    APPROVE_OPERATING_SPEND = "approve_operating_spend"
    ALLOCATE_DEPARTMENT_BUDGET = "allocate_department_budget"
    CHANGE_BUDGET_POLICY = "change_budget_policy"
    APPROVE_RECURRING_PAID_API_SPEND = "approve_recurring_paid_api_spend"

    # -- research, content, production -------------------------------------
    APPROVE_RESEARCH_PROGRAM = "approve_research_program"
    APPROVE_CONTENT_EXPERIMENT = "approve_content_experiment"
    APPROVE_PRODUCTION_RENDER = "approve_production_render"
    PUBLISH_PUBLIC_VIDEO = "publish_public_video"
    DROP_CONTENT_FORMAT = "drop_content_format"

    # -- operations --------------------------------------------------------
    APPROVE_CROSS_DEPARTMENT_SCHEDULE = "approve_cross_department_schedule"
    APPROVE_WORKFORCE_STATE_CHANGE = "approve_workforce_state_change"
    HIRE_OR_REMOVE_EXECUTIVE_ROLE = "hire_or_remove_executive_role"
    DELETE_PRODUCTION_DATA = "delete_production_data"

    # -- governance --------------------------------------------------------
    CHANGE_DELEGATION_POLICY = "change_delegation_policy"
    EXPAND_AUTHORITY = "expand_authority"
    CHANGE_GOVERNANCE_POLICY = "change_governance_policy"
    CHANGE_COMPANY_MISSION = "change_company_mission"
    AMEND_CONSTITUTION = "amend_constitution"
    CHANGE_NO_SUBAGENTS_POLICY = "change_no_subagents_policy"
    APPROVE_SECURITY_EXCEPTION = "approve_security_exception"

    # -- the fail-closed bucket --------------------------------------------
    UNCLASSIFIED = "unclassified"


# Action types that map onto a name in permissions.yaml ceo_reserved.
RESERVED_AS: dict[ActionType, str] = {
    ActionType.PUBLISH_PUBLIC_VIDEO: "publish_public_video",
    ActionType.APPROVE_RECURRING_PAID_API_SPEND: "large_or_recurring_paid_api_spend",
    ActionType.DELETE_PRODUCTION_DATA: "delete_important_production_or_company_data",
    ActionType.APPROVE_ARCHITECTURE_REDESIGN: "merge_major_architecture_rewrite",
    ActionType.CHANGE_PRIMARY_ENGINE: "change_primary_engine",
    ActionType.HIRE_OR_REMOVE_EXECUTIVE_ROLE: "hire_or_remove_executive_role",
    ActionType.DROP_CONTENT_FORMAT: "drop_entire_content_format",
    ActionType.CHANGE_COMPANY_MISSION: "change_company_mission",
    ActionType.AMEND_CONSTITUTION: "amend_constitution",
    ActionType.CHANGE_NO_SUBAGENTS_POLICY: "change_no_subagents_policy",
}

# Reserved by this package, with no corresponding entry in permissions.yaml.
# These are the actions that would let the delegation model widen itself.
RESERVED_HERE: frozenset[ActionType] = frozenset(
    {
        ActionType.CHANGE_DELEGATION_POLICY,
        ActionType.EXPAND_AUTHORITY,
        ActionType.CHANGE_GOVERNANCE_POLICY,
        ActionType.UNCLASSIFIED,
    }
)

# Why each self-reserved action is self-reserved, for the report to quote.
RESERVED_HERE_REASON: dict[ActionType, str] = {
    ActionType.CHANGE_DELEGATION_POLICY: (
        "a delegation policy that can rewrite itself is not a limit"
    ),
    ActionType.EXPAND_AUTHORITY: (
        "no seat may widen its own ceiling; authority is granted, never taken"
    ),
    ActionType.CHANGE_GOVERNANCE_POLICY: (
        "the governance surface is what every other limit is measured against"
    ),
    ActionType.UNCLASSIFIED: (
        "an action nobody classified has no measured risk, so it has no ceiling"
    ),
}


def parse_action(value: Any, field: str = "action") -> ActionType:
    """Decode an action name, refusing one the model does not know."""
    if isinstance(value, ActionType):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be an action name, got {value!r}")
    try:
        return ActionType(value)
    except ValueError as exc:
        raise DelegationError(
            f"{field}: {value!r} is not a known action type. Use "
            f"{ActionType.UNCLASSIFIED.value!r} for an action the model has no "
            "classification for; it is permanently CEO-reserved, which is the "
            "honest answer for an unmeasured risk."
        ) from exc


def _declared(permissions: Mapping[str, Any]) -> frozenset[str]:
    declared = (
        permissions.get("ceo_reserved", ()) if isinstance(permissions, Mapping) else ()
    )
    if isinstance(declared, (str, bytes)) or not isinstance(declared, (list, tuple)):
        raise DelegationError(
            "permissions.yaml ceo_reserved must be a list of action names"
        )
    return frozenset(str(item) for item in declared)


def reserved_action_types(permissions: Mapping[str, Any]) -> frozenset[ActionType]:
    """Every action type the CEO has reserved, read from the canonical list."""
    declared = _declared(permissions)
    from_file = {action for action, name in RESERVED_AS.items() if name in declared}
    return frozenset(from_file | RESERVED_HERE)


@dataclass(frozen=True)
class ReservationDrift:
    """What the mapping and permissions.yaml disagree about, in both directions."""

    released: tuple[str, ...] = ()
    unmapped: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ("company/permissions.yaml",)

    @property
    def ok(self) -> bool:
        """Only a release is drift. A list that grew reserves more, not less."""
        return not self.released


def reservation_drift(permissions: Mapping[str, Any]) -> ReservationDrift:
    """Compare this mapping with the canonical reserved list, both directions.

    `released` names an action this package maps onto a reserved decision that
    `permissions.yaml` no longer reserves — the direction that would quietly
    make something delegable. `unmapped` names a reserved decision this package
    has no action type for; that is a coverage gap worth seeing and not a
    safety failure, because an action with no type cannot be requested at all.
    """
    declared = _declared(permissions)
    released = tuple(
        f"{action.value} maps to {name}, which permissions.yaml no longer reserves"
        for action, name in sorted(RESERVED_AS.items(), key=lambda item: item[0].value)
        if name not in declared
    )
    unmapped = tuple(sorted(declared - set(RESERVED_AS.values())))
    return ReservationDrift(released=released, unmapped=unmapped)


__all__ = [
    "RESERVED_AS",
    "RESERVED_HERE",
    "RESERVED_HERE_REASON",
    "ActionType",
    "ReservationDrift",
    "parse_action",
    "reservation_drift",
    "reserved_action_types",
]

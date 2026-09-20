"""The operating modes Company OS can run in, and the contract each requires.

Two modes exist. There is no third, and adding one is a source change rather
than a configuration value, for the same reason `PROTECTED_REFS` is a constant:
a mode list a policy edit can extend is a mode list that will be extended.

    SHADOW
        The default and the only mode the canonical policy file declares.
        Authority is calculated and recorded; nothing is authorized. Every
        delegated answer is advice.

    BOUNDED_ROUTINE_ENGINEERING
        Ordinary Engineering Department operations, inside one CEO objective
        contract, may proceed without asking the CEO for each step. Nothing
        else changes: the same seats, the same ceilings, the same independent
        controls, the same protected refs.

## What this module is, and what it is not

It is the **gate** between a CEO contract and live authority. It is not a
second authority model: `company/delegation/pilot.py` still answers every
individual request through `evaluate_live`, and this module decides whether a
`PilotActivation` may be built for a given objective at all.

That ordering matters. A mode cannot authorize an action; it can only permit an
activation, which then narrows - never widens - what the shadow calculation
already allowed. Three layers, each strictly more restrictive than the one
above:

    delegation_policy.yaml   who could ever approve this
    ObjectiveContract        what this objective authorized
    evaluate_live            whether this specific request may proceed

## Why the mode is not written into delegation_policy.yaml

`company/delegation/shadow.py` probe 5 asserts on every run that a policy
declaring anything other than `mode: shadow` is refused at construction. That
probe is the guarantee the CEO has been measuring against since the beginning,
and relaxing it to admit a second value would remove the property rather than
extend it.

So the canonical policy file stays `mode: shadow` forever, and an operating
mode lives in a contract the CEO signs per objective. There is no global switch
to leave on, because there is no global switch.
"""

from __future__ import annotations

from collections.abc import Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import Risk
from company.finance.money import Money

from .actions import ActionType, parse_action
from .common import assert_day, assert_prose, assert_record_id, name_tuple, text_tuple
from .errors import DelegationError
from .policy import parse_risk, risk_rank


CONTRACT_VERSION = "objective_contract_v1"


class OperatingMode(str, Enum):
    """How much of its own work the company may finish unaided."""

    SHADOW = "shadow"
    BOUNDED_ROUTINE_ENGINEERING = "bounded_routine_engineering"


#: The one department this mode may operate in. A frozenset of one, rather than
#: a string, because the shape that would be needed to widen it later is the
#: shape that makes widening a reviewed source change today.
BOUNDED_ENGINEERING_DEPARTMENTS: frozenset[str] = frozenset({"engineering"})

#: The highest risk a bounded routine objective may carry. Above this the
#: objective is not routine, whatever it is called.
BOUNDED_ENGINEERING_MAX_RISK: Risk = Risk.MEDIUM

#: What the Engineering Manager may decide inside a bounded objective. This is
#: exactly the set the successful pilot exercised, and no more.
MANAGER_ROUTINE_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.APPROVE_CODE_CHANGE,
        ActionType.APPROVE_REVIEW_OUTCOME,
        ActionType.APPROVE_TEST_PROGRESSION,
        ActionType.REQUEST_BOUNDED_CORRECTION,
        ActionType.STOP_WORK_ON_INVALID_PREMISE,
    }
)

#: What the CTO may decide inside a bounded objective, in addition to anything
#: the manager may. Integration is here and nowhere else.
CTO_ROUTINE_ACTIONS: frozenset[ActionType] = frozenset(
    {ActionType.APPROVE_INTEGRATION_MERGE}
) | MANAGER_ROUTINE_ACTIONS

#: The closed set a bounded engineering contract may name. An action outside it
#: is not refused later - the contract refuses to exist.
BOUNDED_ENGINEERING_ACTIONS: frozenset[ActionType] = CTO_ROUTINE_ACTIONS | {
    ActionType.APPROVE_WORK_ORDER,
    ActionType.SELECT_WORK,
    ActionType.DISCOVER_WORK,
}

#: Actions no objective contract may name, whatever the CEO writes in it. These
#: are refused at construction rather than at decision time, so a contract that
#: would have been dangerous never exists to be passed around.
#:
#: `approve_canonical_merge` is here because canonical promotion is a separate
#: capability this mode deliberately does not grant; see
#: `docs/company_os_bounded_engineering_autonomy.md`.
CONTRACT_FORBIDDEN: frozenset[ActionType] = frozenset(
    {
        ActionType.APPROVE_DEPLOYMENT,
        ActionType.APPROVE_STAGING_RELEASE,
        ActionType.APPROVE_PRODUCTION_RENDER,
        ActionType.APPROVE_CANONICAL_MERGE,
        ActionType.CHANGE_DELEGATION_POLICY,
        ActionType.CHANGE_BUDGET_POLICY,
        ActionType.APPROVE_WORKFORCE_STATE_CHANGE,
        ActionType.ALLOCATE_DEPARTMENT_BUDGET,
    }
)


@dataclass(frozen=True)
class ObjectiveContract:
    """One CEO objective, and everything the company may do to advance it.

    The CEO signs this once. They do not then approve the work orders, the code
    changes, the review outcomes or the internal integration that follow from
    it - that is the whole point of the mode. What they retain is the shape of
    the box: budget, risk, department, actions, expiry, correction ceiling, and
    what they must be told at the end.

    Frozen, and fingerprinted, because an objective whose terms can drift is
    not a boundary.
    """

    contract_id: str
    objective_id: str
    objective: str
    mode: OperatingMode
    department: str
    budget: Money
    budget_scope: str
    risk_ceiling: Risk
    expires_on: dt.date
    authorized_by: str
    success_criteria: tuple[str, ...] = ()
    allowed_actions: tuple[ActionType, ...] = ()
    forbidden_actions: tuple[ActionType, ...] = ()
    max_corrections_per_work_order: int = 1
    #: What the CEO is owed when the objective ends, whatever the outcome.
    reporting_requirements: tuple[str, ...] = (
        "a final executive outcome report",
        "every management decision and who took it",
        "total model cost against the authorized budget",
        "any exception that ended the objective early",
    )
    notes: str = ""
    version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "contract_id", assert_record_id(self.contract_id, "contract_id")
        )
        object.__setattr__(
            self, "objective_id", assert_record_id(self.objective_id, "objective_id")
        )
        object.__setattr__(
            self, "objective", assert_prose(self.objective, "objective")
        )
        if not isinstance(self.mode, OperatingMode):
            raise DelegationError("contract.mode must be an OperatingMode")
        object.__setattr__(
            self, "department", assert_prose(self.department, "department").lower()
        )
        if not isinstance(self.budget, Money):
            raise DelegationError("contract.budget must be Money")
        object.__setattr__(
            self, "budget_scope", assert_prose(self.budget_scope, "budget_scope")
        )
        object.__setattr__(
            self, "risk_ceiling", parse_risk(self.risk_ceiling, "risk_ceiling")
        )
        object.__setattr__(
            self, "expires_on", assert_day(self.expires_on, "expires_on")
        )
        object.__setattr__(
            self, "authorized_by", assert_prose(self.authorized_by, "authorized_by")
        )
        object.__setattr__(
            self,
            "success_criteria",
            text_tuple(self.success_criteria, "success_criteria", limit=16),
        )
        object.__setattr__(
            self,
            "reporting_requirements",
            text_tuple(
                self.reporting_requirements, "reporting_requirements", limit=16
            ),
        )
        for field in ("allowed_actions", "forbidden_actions"):
            raw = getattr(self, field)
            if isinstance(raw, (str, bytes)) or not isinstance(raw, (list, tuple)):
                raise DelegationError(f"contract.{field} must be a sequence")
            object.__setattr__(
                self,
                field,
                tuple(
                    sorted(
                        {parse_action(item, f"contract.{field}") for item in raw},
                        key=lambda item: item.value,
                    )
                ),
            )
        if isinstance(self.max_corrections_per_work_order, bool) or not isinstance(
            self.max_corrections_per_work_order, int
        ):
            raise DelegationError("contract.max_corrections_per_work_order must be int")
        if not 0 <= self.max_corrections_per_work_order <= 4:
            raise DelegationError(
                "contract.max_corrections_per_work_order is 0..4; a routine objective "
                "that needs a fifth correction is not routine"
            )

        # --- the refusals ---------------------------------------------------
        if self.authorized_by.strip().lower() in {
            "company_os",
            "company-os",
            "system",
            "",
        }:
            raise DelegationError(
                "contract.authorized_by must name a person; a contract this "
                "subsystem can sign for itself is not a boundary"
            )
        overlap = set(self.allowed_actions) & set(self.forbidden_actions)
        if overlap:
            raise DelegationError(
                "contract names "
                + ", ".join(sorted(item.value for item in overlap))
                + " as both allowed and forbidden"
            )
        banned = set(self.allowed_actions) & CONTRACT_FORBIDDEN
        if banned:
            raise DelegationError(
                "no objective contract may allow "
                + ", ".join(sorted(item.value for item in banned))
                + "; these are CEO decisions or separate capabilities, not routine "
                "engineering"
            )
        if self.mode is OperatingMode.SHADOW:
            if self.allowed_actions:
                raise DelegationError(
                    "a shadow contract authorizes nothing and may not name allowed "
                    "actions"
                )
            return

        # --- bounded routine engineering ------------------------------------
        if self.department not in BOUNDED_ENGINEERING_DEPARTMENTS:
            raise DelegationError(
                f"bounded routine engineering covers "
                f"{', '.join(sorted(BOUNDED_ENGINEERING_DEPARTMENTS))}, not "
                f"{self.department}"
            )
        if risk_rank(self.risk_ceiling) > risk_rank(BOUNDED_ENGINEERING_MAX_RISK):
            raise DelegationError(
                f"bounded routine engineering stops at "
                f"{BOUNDED_ENGINEERING_MAX_RISK.value} risk; this contract declares "
                f"{self.risk_ceiling.value}"
            )
        if not self.allowed_actions:
            raise DelegationError(
                "a bounded routine engineering contract that allows no action "
                "authorizes nothing and should be a shadow contract"
            )
        outside = set(self.allowed_actions) - BOUNDED_ENGINEERING_ACTIONS
        if outside:
            raise DelegationError(
                "bounded routine engineering does not cover "
                + ", ".join(sorted(item.value for item in outside))
            )
        if not self.success_criteria:
            raise DelegationError(
                "a live contract states how the company will know it succeeded; "
                "an objective with no success criteria cannot be reported on"
            )

    # --- questions the runtime asks ----------------------------------------

    def is_live(self) -> bool:
        return self.mode is not OperatingMode.SHADOW

    def expired_on(self, day: dt.date) -> bool:
        return assert_day(day, "day") > self.expires_on

    def covers_action(self, action: Any) -> bool:
        parsed = parse_action(action, "action")
        if parsed in self.forbidden_actions or parsed in CONTRACT_FORBIDDEN:
            return False
        return parsed in self.allowed_actions

    def covers_risk(self, risk: Any) -> bool:
        return risk_rank(parse_risk(risk, "risk")) <= risk_rank(self.risk_ceiling)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "objective_id": self.objective_id,
            "objective": self.objective,
            "mode": self.mode.value,
            "department": self.department,
            "budget": self.budget.to_dict(),
            "budget_scope": self.budget_scope,
            "risk_ceiling": self.risk_ceiling.value,
            "expires_on": self.expires_on.isoformat(),
            "authorized_by": self.authorized_by,
            "success_criteria": list(self.success_criteria),
            "allowed_actions": [item.value for item in self.allowed_actions],
            "forbidden_actions": [item.value for item in self.forbidden_actions],
            "max_corrections_per_work_order": self.max_corrections_per_work_order,
            "reporting_requirements": list(self.reporting_requirements),
            "notes": self.notes,
            "version": self.version,
        }


@dataclass(frozen=True)
class ModeVerdict:
    """Whether a contract may be activated, and why not when it may not."""

    contract_id: str
    mode: OperatingMode
    may_activate: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "mode": self.mode.value,
            "may_activate": self.may_activate,
            "reason": self.reason,
        }


def may_activate(
    contract: ObjectiveContract,
    *,
    as_of: dt.date,
    enabled_modes: Sequence[OperatingMode] = (OperatingMode.SHADOW,),
) -> ModeVerdict:
    """Whether this contract may produce a live activation today.

    `enabled_modes` is passed by the caller rather than read from a file, for
    the same reason `evaluate_live` takes an activation rather than consulting
    a flag: the decision to run live has to appear at a call site a reviewer can
    see. The default is shadow only, so forgetting the argument cannot enable
    anything.
    """
    if not isinstance(contract, ObjectiveContract):
        raise DelegationError("may_activate takes an ObjectiveContract")
    enabled = {
        item if isinstance(item, OperatingMode) else OperatingMode(str(item))
        for item in enabled_modes
    }
    if not contract.is_live():
        return ModeVerdict(
            contract_id=contract.contract_id,
            mode=contract.mode,
            may_activate=False,
            reason="a shadow contract authorizes nothing; this is the default",
        )
    if contract.mode not in enabled:
        return ModeVerdict(
            contract_id=contract.contract_id,
            mode=contract.mode,
            may_activate=False,
            reason=(
                f"{contract.mode.value} is not enabled in this deployment; the CEO "
                "activates an operating mode explicitly and it is not on"
            ),
        )
    if contract.expired_on(as_of):
        return ModeVerdict(
            contract_id=contract.contract_id,
            mode=contract.mode,
            may_activate=False,
            reason=(
                f"the contract expired on {contract.expires_on.isoformat()} and "
                f"today is {as_of.isoformat()}"
            ),
        )
    return ModeVerdict(
        contract_id=contract.contract_id,
        mode=contract.mode,
        may_activate=True,
        reason=(
            f"{contract.mode.value} is enabled, the contract is signed by "
            f"{contract.authorized_by} and runs to "
            f"{contract.expires_on.isoformat()}"
        ),
    )


__all__ = [
    "BOUNDED_ENGINEERING_ACTIONS",
    "BOUNDED_ENGINEERING_DEPARTMENTS",
    "BOUNDED_ENGINEERING_MAX_RISK",
    "CONTRACT_FORBIDDEN",
    "CONTRACT_VERSION",
    "CTO_ROUTINE_ACTIONS",
    "MANAGER_ROUTINE_ACTIONS",
    "ModeVerdict",
    "ObjectiveContract",
    "OperatingMode",
    "may_activate",
]

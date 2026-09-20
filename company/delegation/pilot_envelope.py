"""The smallest thing a CEO can sign that lets an organization act without them.

## The one field the shadow envelope was missing

`objectives.PlanningEnvelope` already carries budget, risk ceiling, allowed
departments, forbidden actions, success metrics and a deadline. It was enough
for shadow, because in shadow nothing it permits actually happens.

It has a *deny-list* of actions and no allow-list. That asymmetry is safe when
the envelope only annotates a calculation and unsafe the moment the envelope
authorizes one: a deny-list authorizes every action nobody thought to forbid,
including every action added to `ActionType` after the envelope was signed. A
pilot built on a deny-list would silently widen itself with the next commit
that adds an action.

So `PilotEnvelope` composes the planning envelope and adds the allow-list. The
two are kept as separate objects rather than merged because the planning
envelope is canonical and shadow-safe and this one is not: a reader can see at
a glance which half the CEO signed for shadow and which half they signed for
live authority.

## Why expiry is required and not optional

`PlanningEnvelope.deadline` is optional, and for a plan that is right — an
objective without a date is a bad plan, not an unsafe one. For delegated
authority it is the opposite. An envelope with no expiry is a standing grant,
and a standing grant is what this pilot is specifically not. So `expires_on` is
required here, it is checked against the day a decision is taken rather than
the day the envelope was built, and an expired envelope escalates rather than
refusing: the work is legitimate, the authority to approve it is what ran out.

## What "smallest" means

Every field below answers a question the authority calculation actually asks.
There is deliberately nothing here about *how* to achieve the objective, no
task list, and no approval thresholds that duplicate the policy's own ceilings.
The envelope is a boundary, and the organization plans inside it.
"""

from __future__ import annotations

from collections.abc import Iterable
import datetime as dt
from dataclasses import dataclass
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import RESERVED_HERE, ActionType, parse_action
from .common import assert_day, assert_prose, assert_record_id, positive_int, text_tuple
from .errors import DelegationError, PilotBoundaryViolation
from .objectives import PlanningEnvelope
from .pilot_integration import IntegrationTarget
from .policy import parse_risk, risk_rank


ENVELOPE_VERSION = "pilot_envelope_v1"


def _action_set(values: Iterable[Any], field: str) -> tuple[ActionType, ...]:
    parsed = tuple(parse_action(item, field) for item in (values or ()))
    return tuple(sorted(set(parsed), key=lambda item: item.value))


@dataclass(frozen=True)
class PilotEnvelope:
    """What the CEO authorized, as a boundary the organization plans inside.

    `plan` carries the budget, risk ceiling, allowed departments, success
    metrics and forbidden actions. This object adds the three things live
    authority needs and a plan does not: the closed set of actions that may be
    approved without the CEO, the place work may be accepted, and the day the
    authority stops.
    """

    envelope_id: str
    objective: str
    plan: PlanningEnvelope
    allowed_actions: tuple[ActionType, ...]
    integration_target: IntegrationTarget
    expires_on: dt.date
    # The named human who signed this. "company_os" and friends are refused:
    # an envelope this subsystem could sign for itself is not a boundary.
    authorized_by: str = ""
    # How many bounded corrections the organization may authorize per work
    # order before the CEO hears about it. Checked against the resource profile
    # by `pilot_correction.py`; stored here because it is a CEO choice.
    max_corrections_per_work_order: int = 1
    success_criteria: tuple[str, ...] = ()
    notes: str = ""
    version: str = ENVELOPE_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "envelope_id",
            assert_record_id(self.envelope_id, "envelope.envelope_id"),
        )
        object.__setattr__(
            self, "objective", assert_prose(self.objective, "envelope.objective")
        )
        if not isinstance(self.plan, PlanningEnvelope):
            raise DelegationError("envelope.plan must be a PlanningEnvelope")
        if not isinstance(self.integration_target, IntegrationTarget):
            raise DelegationError(
                "envelope.integration_target must be an IntegrationTarget"
            )
        object.__setattr__(
            self, "expires_on", assert_day(self.expires_on, "envelope.expires_on")
        )
        object.__setattr__(
            self,
            "authorized_by",
            assert_prose(self.authorized_by, "envelope.authorized_by"),
        )
        object.__setattr__(
            self,
            "max_corrections_per_work_order",
            positive_int(
                self.max_corrections_per_work_order,
                "envelope.max_corrections_per_work_order",
                minimum=0,
                maximum=8,
            ),
        )
        object.__setattr__(
            self,
            "success_criteria",
            text_tuple(self.success_criteria, "envelope.success_criteria", limit=12),
        )
        object.__setattr__(
            self, "notes", assert_prose(self.notes, "envelope.notes") if self.notes else ""
        )
        if self.version != ENVELOPE_VERSION:
            raise DelegationError(f"envelope.version must be {ENVELOPE_VERSION!r}")

        allowed = _action_set(self.allowed_actions, "envelope.allowed_actions")
        object.__setattr__(self, "allowed_actions", allowed)
        if not allowed:
            raise PilotBoundaryViolation(
                f"envelope {self.envelope_id!r} names no allowed action. An envelope "
                "with an empty allow-list authorizes nothing, and an envelope that "
                "authorizes nothing should not be activated rather than being treated "
                "as permitting everything."
            )

        # An envelope may not allow what this package reserves to itself. That
        # set is a constant, so it is checked here with no I/O: these are the
        # actions that would let the envelope widen the envelope.
        #
        # The larger reserved set — everything permissions.yaml reserves — is
        # checked by `reserved_overlap` at activation, because only the
        # activation holds the policy that read the file. Two layers on purpose:
        # this one cannot be bypassed by constructing an envelope by hand, and
        # that one stays authoritative about the canonical list.
        overlap = tuple(item for item in allowed if item in RESERVED_HERE)
        if overlap:
            names = ", ".join(item.value for item in overlap)
            raise PilotBoundaryViolation(
                f"envelope {self.envelope_id!r} allows self-reserved action(s): "
                f"{names}. These are the actions that would let a delegated seat "
                "widen its own authority, and no envelope can grant them."
            )

        # The allow-list and the plan's deny-list must not contradict each
        # other. Silently preferring one would make the envelope unreadable.
        contradiction = tuple(
            item for item in allowed if item in self.plan.forbidden_actions
        )
        if contradiction:
            names = ", ".join(item.value for item in contradiction)
            raise DelegationError(
                f"envelope {self.envelope_id!r} both allows and forbids: {names}. The "
                "plan's forbidden_actions and this envelope's allowed_actions "
                "disagree; resolve it in the envelope rather than letting the code "
                "pick a winner."
            )

        if self.plan.deadline is not None and self.expires_on > self.plan.deadline:
            raise DelegationError(
                f"envelope {self.envelope_id!r} expires {self.expires_on.isoformat()}, "
                f"after the objective deadline {self.plan.deadline.isoformat()}. "
                "Authority cannot outlive the objective it was granted for."
            )

        forbidden_signer = {"company_os", "company-os", "system", "automatic", ""}
        if self.authorized_by.strip().lower().replace(" ", "_") in forbidden_signer:
            raise PilotBoundaryViolation(
                "envelope.authorized_by must name the human CEO who signed this "
                f"envelope, not {self.authorized_by!r}. An envelope this subsystem "
                "could sign for itself is not a boundary, it is a preference."
            )

    # --- what the calculation asks it --------------------------------------

    @property
    def budget(self) -> Money:
        return self.plan.budget

    @property
    def budget_scope(self) -> str:
        return self.plan.budget_scope

    @property
    def risk_ceiling(self) -> Risk:
        return self.plan.risk_ceiling

    @property
    def objective_id(self) -> str:
        return self.plan.objective_id

    def expired_on(self, day: Any) -> bool:
        """True when the authority has run out as of `day`."""
        return assert_day(day, "envelope.as_of") > self.expires_on

    def permits_action(self, action: Any) -> bool:
        parsed = parse_action(action, "envelope.action")
        return parsed in self.allowed_actions

    def permits_department(self, department: Any) -> bool:
        name = str(department or "").strip().lower()
        return bool(name) and name in self.plan.allowed_departments

    def permits_risk(self, risk: Any) -> bool:
        parsed = parse_risk(risk, "envelope.risk")
        return risk_rank(parsed) <= risk_rank(self.risk_ceiling)

    def permits_amount(self, amount: Money | None) -> bool:
        if amount is None:
            return True
        if amount.currency != self.budget.currency:
            # Not comparable, so not permitted. A currency mismatch is a
            # malformed request rather than a large one, and the honest answer
            # is "this envelope cannot say", which fails closed.
            return False
        return amount <= self.budget

    def reserved_overlap(
        self, reserved: frozenset[ActionType] | set[ActionType]
    ) -> tuple[ActionType, ...]:
        """Allowed actions that the canonical reserved list forbids.

        Called by `pilot_activation` with `DelegationPolicy.reserved`, which is
        `permissions.yaml` plus this package's own set. Returned rather than
        raised so the activation can name every one of them at once.
        """
        return tuple(item for item in self.allowed_actions if item in reserved)

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "objective": self.objective,
            "plan": self.plan.to_dict(),
            "allowed_actions": [item.value for item in self.allowed_actions],
            "integration_target": self.integration_target.to_dict(),
            "expires_on": self.expires_on.isoformat(),
            "authorized_by": self.authorized_by,
            "max_corrections_per_work_order": self.max_corrections_per_work_order,
            "success_criteria": list(self.success_criteria),
            "notes": self.notes,
            "version": self.version,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


__all__ = ["ENVELOPE_VERSION", "PilotEnvelope"]

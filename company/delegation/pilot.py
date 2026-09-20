"""Live delegated authority, for one bounded class of decisions, opt-in only.

## What is different here, in one sentence

Everywhere else in this package a decision says *who would be competent*. Here,
for a closed set of actions inside a signed envelope, a decision says *this is
approved* — and carries `authorizes_action=True`, the flag every other object in
`company/delegation` refuses to set.

## Why this is a separate layer and not a mode on the existing policy

`DelegationPolicy.__post_init__` refuses any mode but `shadow`, and
`shadow.py` probe 5 asserts that refusal against the canonical class on every
run. The obvious implementation — add `LIVE_PILOT` to `DelegationMode` and
relax that check — would have made the canonical policy able to leave shadow
mode, which is exactly the property the CEO asked to preserve.

So the canonical policy is untouched and still refuses. This module is a layer
*on top* of it: it calls the canonical `evaluate` for the authority
calculation, keeps that answer as the floor, and then applies the pilot's own
gates. The consequence is the property that matters:

    importing this module changes nothing.
    constructing a PilotActivation changes nothing.
    only passing one to `evaluate_live` decides anything.

Default behaviour is therefore shadow by construction rather than by
configuration. There is no flag to leave set wrongly, because there is no flag.

## The floor rule

A pilot gate can only ever make the answer *narrower*. `evaluate_live` never
approves something the canonical shadow calculation escalated, never moves the
approving seat, and never lowers `ceo_required` from True to False. It can turn
an APPROVED into an ESCALATE; it can never do the reverse. Every test in
section 4 of `tests/test_company_delegation_pilot.py` exists to hold that line,
because it is the difference between a pilot and a bypass.

## Why the approval is still not the act

`authorizes_action=True` means "a seat with the authority to approve this has
approved it". It does not merge, deploy, publish, spawn a process or write to a
production tree — this package still cannot do any of those, and the gate check
`production.no_publishing_capability` still scans it for the capability. The
act remains somebody else's, performed against a decision record that names who
authorized it. That is the same separation the engineering plane already has
between `decision.py` and the runner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import RESERVED_HERE, ActionType, parse_action
from .authority import (
    AuthorityDecision,
    AuthorityRequest,
    ChainStep,
    Decision,
    evaluate,
)
from .common import assert_day, assert_prose, assert_record_id
from .deployment import DEPLOYMENT_POLICY, DeploymentClass, DeploymentKind
from .errors import DelegationError, PilotBoundaryViolation
from .org import CEO_SEAT
from .pilot_envelope import PilotEnvelope
from .pilot_integration import PROTECTED_REFS, IntegrationTarget, TargetKind
from .policy import DelegationPolicy, risk_rank


PILOT_VERSION = "delegated_engineering_pilot_v1"


class PilotMode(str, Enum):
    """Whether a decision was advice or authority, as written into the record.

    Deliberately not `DelegationMode`. That enum belongs to the canonical
    policy, which still has one legal value; this one describes what a *record*
    was produced under, and a store may legitimately hold both kinds.
    """

    SHADOW = "shadow"
    LIVE_PILOT = "live_pilot"


class PilotGateId(str, Enum):
    """Every reason the pilot narrows an answer the shadow model allowed."""

    NOT_ACTIVATED = "not_activated"
    SEAT_NOT_IN_PILOT = "seat_not_in_pilot"
    ACTION_NOT_IN_PILOT = "action_not_in_pilot"
    ACTION_NOT_IN_ENVELOPE = "action_not_in_envelope"
    RISK_ABOVE_PILOT_CEILING = "risk_above_pilot_ceiling"
    RISK_ABOVE_ENVELOPE = "risk_above_envelope"
    DEPARTMENT_NOT_IN_ENVELOPE = "department_not_in_envelope"
    AMOUNT_ABOVE_ENVELOPE = "amount_above_envelope"
    ENVELOPE_EXPIRED = "envelope_expired"
    OBJECTIVE_MISMATCH = "objective_mismatch"
    PROTECTED_REF = "protected_ref"
    TARGET_NOT_PERMITTED = "target_not_permitted"
    DEPLOYMENT_NOT_ROUTINE = "deployment_not_routine"
    CORRECTION_CEILING = "correction_ceiling"
    REVIEW_NOT_INDEPENDENT = "review_not_independent"
    QA_NOT_PASSED = "qa_not_passed"


@dataclass(frozen=True)
class PilotGate:
    """One pilot condition, whether it held, and what it means if it did not."""

    gate_id: PilotGateId
    held: bool
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.gate_id, PilotGateId):
            raise DelegationError("gate.gate_id must be a PilotGateId value")
        if not isinstance(self.held, bool):
            raise DelegationError("gate.held must be a boolean")
        object.__setattr__(self, "detail", assert_prose(self.detail, "gate.detail"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id.value,
            "held": self.held,
            "detail": self.detail,
        }


# --- the live action set --------------------------------------------------
#
# These are transcribed from the CEO's pilot authorization, and they are a
# *subset* of what company/delegation_policy.yaml already grants each seat. The
# policy is the ceiling; this is the pilot. Where they differ the narrower one
# wins, which is always this one.

# The Engineering Manager's live set: routine progression of engineering work
# that has already passed an independent control.
ENGINEERING_MANAGER_LIVE_ACTIONS: frozenset[ActionType] = frozenset(
    {
        # low-risk routine engineering work
        ActionType.APPROVE_WORK_ORDER,
        ActionType.APPROVE_CODE_CHANGE,
        # transition after a successful independent review
        ActionType.APPROVE_REVIEW_OUTCOME,
        # ordinary continuation to deterministic QA
        ActionType.APPROVE_TEST_PROGRESSION,
        # a bounded correction after reviewer changes_required
        ActionType.REQUEST_BOUNDED_CORRECTION,
        # stopping work is always allowed: it can only narrow what happens
        ActionType.STOP_WORK_ON_INVALID_PREMISE,
    }
)

# The CTO's live set: the manager's set, plus the internal integration decision
# the manager may continue *to* but not decide.
#
# `APPROVE_INTEGRATION_MERGE` and not `APPROVE_LOCAL_INTEGRATION`, which looks
# backwards and is not. `delegation_policy.yaml` grants the CTO
# `approve_integration_merge`; it grants `approve_local_integration` to nobody
# at all, despite `deployment.py` classifying that one as routine-delegatable.
# Putting the ungranted action in this set would advertise authority that does
# not exist: the floor rule would escalate every such request, and the pilot
# would look broken rather than narrow. The mismatch between the two is a real
# gap in the canonical policy and is reported as a known limitation rather than
# fixed here, because closing it means editing a grant, which is a CEO decision.
CTO_LIVE_ACTIONS: frozenset[ActionType] = frozenset(
    ENGINEERING_MANAGER_LIVE_ACTIONS | {ActionType.APPROVE_INTEGRATION_MERGE}
)

# The actions that land work somewhere, and therefore need an integration
# target checked. Kept separate from the grant sets because it is a question
# about the action's *effect*, not about who may take it.
INTEGRATING_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.APPROVE_INTEGRATION_MERGE,
        ActionType.APPROVE_LOCAL_INTEGRATION,
    }
)

# The risk ceiling each pilot seat may live-approve at.
#
# The Engineering Manager is LOW, exactly as the CEO specified and exactly as
# delegation_policy.yaml already grants. The CTO is MEDIUM *only because* the
# existing delegated policy explicitly allows it (`cto.max_risk: medium`); the
# pilot does not widen anybody. If that grant were narrowed the pilot would
# narrow with it, because `_seat_ceiling` takes the minimum of the two.
PILOT_RISK_CEILING: Mapping[str, Risk] = {
    "engineering_manager": Risk.LOW,
    "cto": Risk.MEDIUM,
}

# The seats this pilot grants live authority to. Nobody else, at any risk.
PILOT_SEATS: Mapping[str, frozenset[ActionType]] = {
    "engineering_manager": ENGINEERING_MANAGER_LIVE_ACTIONS,
    "cto": CTO_LIVE_ACTIONS,
}

# Actions no pilot seat may live-approve, whatever an envelope says. This is
# belt-and-braces over the reserved set: several of these are not CEO-reserved
# in permissions.yaml (a staging release, for instance, is executive rather
# than CEO) and are still outside *this* pilot.
PILOT_FORBIDDEN_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.APPROVE_CANONICAL_MERGE,
        ActionType.APPROVE_STAGING_RELEASE,
        ActionType.APPROVE_DEPLOYMENT,
        ActionType.PUBLISH_PUBLIC_VIDEO,
        ActionType.APPROVE_ARCHITECTURE_REDESIGN,
        ActionType.CHANGE_PRIMARY_ENGINE,
        ActionType.APPROVE_SECURITY_EXCEPTION,
        ActionType.HIRE_OR_REMOVE_EXECUTIVE_ROLE,
        ActionType.DELETE_PRODUCTION_DATA,
        ActionType.CHANGE_BUDGET_POLICY,
        ActionType.APPROVE_RECURRING_PAID_API_SPEND,
        ActionType.DROP_CONTENT_FORMAT,
        ActionType.CHANGE_COMPANY_MISSION,
        ActionType.AMEND_CONSTITUTION,
        ActionType.CHANGE_NO_SUBAGENTS_POLICY,
    }
    | RESERVED_HERE
)

# Why each is outside the pilot, for a refusal that explains itself.
PILOT_FORBIDDEN_REASON: Mapping[ActionType, str] = {
    ActionType.APPROVE_CANONICAL_MERGE: (
        "moving the canonical branch is what everything downstream builds on; the "
        "pilot accepts work onto its own internal branch instead"
    ),
    ActionType.APPROVE_STAGING_RELEASE: (
        "a build, even an internal one, is a release rather than an integration"
    ),
    ActionType.APPROVE_DEPLOYMENT: "public deployment is CEO-reserved for this pilot",
    ActionType.PUBLISH_PUBLIC_VIDEO: (
        "a published video has been seen and cannot be unpublished"
    ),
    ActionType.APPROVE_ARCHITECTURE_REDESIGN: (
        "major architecture is a CEO decision and the pilot is routine work only"
    ),
    ActionType.APPROVE_SECURITY_EXCEPTION: (
        "a security exception is a governance change wearing an engineering hat"
    ),
}


def _seat_ceiling(seat: str, policy: DelegationPolicy) -> Risk:
    """The lower of the pilot's ceiling and the policy's own grant.

    Taking the minimum is what makes the pilot unable to widen anybody: if the
    CEO later narrows `cto.max_risk` to low in the YAML, the pilot narrows with
    it without this file changing.
    """
    pilot = PILOT_RISK_CEILING.get(seat)
    if pilot is None:
        return Risk.LOW
    grant = policy.grant(seat)
    granted = getattr(grant, "max_risk", None)
    if granted is None:
        # The seat is in the pilot table but the policy grants it nothing. The
        # pilot cannot be the only source of authority, so the honest ceiling is
        # the lowest one; the seat gate will refuse it anyway.
        return Risk.LOW
    return pilot if risk_rank(pilot) <= risk_rank(granted) else granted


@dataclass(frozen=True)
class PilotActivation:
    """The CEO's explicit, dated, bounded opt-in to live delegated authority.

    Constructing one of these does not activate anything: it is the token that
    `evaluate_live` requires, and without it every request falls back to the
    shadow answer. It is a frozen dataclass rather than a config file because a
    live grant should have to be passed by hand at the call site, where a reader
    can see it.
    """

    activation_id: str
    envelope: PilotEnvelope
    activated_by: str
    activated_on: dt.date
    # The caller must pass this explicitly. A default of True would make live
    # authority the thing you get by forgetting a keyword argument.
    acknowledged_live: bool = False
    mode: PilotMode = PilotMode.LIVE_PILOT
    policy_version: str = ""
    notes: str = ""
    version: str = PILOT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "activation_id",
            assert_record_id(self.activation_id, "activation.activation_id"),
        )
        if not isinstance(self.envelope, PilotEnvelope):
            raise DelegationError("activation.envelope must be a PilotEnvelope")
        object.__setattr__(
            self,
            "activated_by",
            assert_prose(self.activated_by, "activation.activated_by"),
        )
        object.__setattr__(
            self,
            "activated_on",
            assert_day(self.activated_on, "activation.activated_on"),
        )
        if not isinstance(self.acknowledged_live, bool):
            raise DelegationError("activation.acknowledged_live must be a boolean")
        if not isinstance(self.mode, PilotMode):
            raise DelegationError("activation.mode must be a PilotMode value")
        object.__setattr__(
            self,
            "policy_version",
            assert_prose(self.policy_version, "activation.policy_version")
            if self.policy_version
            else "",
        )
        object.__setattr__(
            self, "notes", assert_prose(self.notes, "activation.notes") if self.notes else ""
        )
        if self.version != PILOT_VERSION:
            raise DelegationError(f"activation.version must be {PILOT_VERSION!r}")

        if not self.acknowledged_live:
            raise PilotBoundaryViolation(
                f"activation {self.activation_id!r} did not set "
                "acknowledged_live=True. Live delegated authority is opt-in at the "
                "call site: an activation that can be built by default is an "
                "activation somebody will build by accident."
            )
        if self.mode is not PilotMode.LIVE_PILOT:
            raise DelegationError(
                "activation.mode is the live-pilot mode; a shadow activation is just "
                "the absence of an activation, which is the default"
            )

        automatic = {"company_os", "company-os", "system", "automatic", ""}
        if self.activated_by.strip().lower().replace(" ", "_") in automatic:
            raise PilotBoundaryViolation(
                "activation.activated_by must name the human who activated the "
                f"pilot, not {self.activated_by!r}. This subsystem cannot activate "
                "itself; that is the whole point of an activation."
            )
        if self.activated_on > self.envelope.expires_on:
            raise PilotBoundaryViolation(
                f"activation {self.activation_id!r} is dated "
                f"{self.activated_on.isoformat()}, after its envelope expired on "
                f"{self.envelope.expires_on.isoformat()}. Authority cannot be "
                "activated retroactively past its own expiry."
            )

    def check_against(self, policy: DelegationPolicy) -> None:
        """Refuse an activation the canonical policy contradicts.

        Called by `evaluate_live` on every request rather than once at
        construction, because the policy is loaded from YAML and the file can
        change under a long-lived activation.
        """
        overlap = self.envelope.reserved_overlap(policy.reserved)
        if overlap:
            names = ", ".join(item.value for item in overlap)
            raise PilotBoundaryViolation(
                f"activation {self.activation_id!r} allows reserved action(s): "
                f"{names}. company/permissions.yaml reserves these to the CEO and "
                "an envelope cannot release them."
            )
        forbidden = tuple(
            item
            for item in self.envelope.allowed_actions
            if item in PILOT_FORBIDDEN_ACTIONS
        )
        if forbidden:
            names = ", ".join(item.value for item in forbidden)
            raise PilotBoundaryViolation(
                f"activation {self.activation_id!r} allows action(s) outside this "
                f"pilot: {names}. The pilot covers routine low-risk engineering "
                "management; widening it is a separate CEO decision."
            )

    @property
    def integration_target(self) -> IntegrationTarget:
        return self.envelope.integration_target

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation_id": self.activation_id,
            "envelope": self.envelope.to_dict(),
            "activated_by": self.activated_by,
            "activated_on": self.activated_on.isoformat(),
            "acknowledged_live": self.acknowledged_live,
            "mode": self.mode.value,
            "policy_version": self.policy_version,
            "notes": self.notes,
            "version": self.version,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


@dataclass(frozen=True)
class PilotRequest:
    """A shadow request plus the three facts live authority has to know.

    Composition rather than a subclass: `AuthorityRequest` is canonical and
    validated, and the pilot needs it unchanged to call `evaluate`. What it adds
    is where the work would land, whether an independent review passed, and
    whether deterministic QA passed — none of which shadow needed, because
    shadow never let anything proceed.
    """

    request: AuthorityRequest
    # The branch the decision would advance, when the action integrates.
    integration_branch: str = ""
    # The reviewer verdict, when there is one. `None` means "no review has run",
    # which is different from a failed one and is treated as such.
    review_passed: bool | None = None
    # The deterministic QA verdict, same three-valued convention.
    qa_passed: bool | None = None
    # Corrections already authorized for this work order.
    corrections_used: int = 0
    # The day the decision is being taken, for expiry.
    as_of: dt.date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, AuthorityRequest):
            raise DelegationError("pilot_request.request must be an AuthorityRequest")
        if self.integration_branch:
            object.__setattr__(
                self,
                "integration_branch",
                assert_prose(self.integration_branch, "pilot_request.integration_branch"),
            )
        for name in ("review_passed", "qa_passed"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise DelegationError(
                    f"pilot_request.{name} must be True, False or None"
                )
        if isinstance(self.corrections_used, bool) or not isinstance(
            self.corrections_used, int
        ):
            raise DelegationError("pilot_request.corrections_used must be an integer")
        if self.corrections_used < 0:
            raise DelegationError("pilot_request.corrections_used is not negative")
        if self.as_of is not None:
            object.__setattr__(
                self, "as_of", assert_day(self.as_of, "pilot_request.as_of")
            )

    @property
    def action(self) -> ActionType:
        return self.request.action

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "integration_branch": self.integration_branch,
            "review_passed": self.review_passed,
            "qa_passed": self.qa_passed,
            "corrections_used": self.corrections_used,
            "as_of": self.as_of.isoformat() if self.as_of else None,
        }


@dataclass(frozen=True)
class LivePilotDecision:
    """A live delegated answer: the shadow calculation, narrowed, and acted on.

    `authorizes_action` is the one field in this package that may be True, and
    it may only be True when every one of `gates` held and the underlying
    shadow decision was already an approval by a pilot seat.
    """

    request_id: str
    mode: PilotMode
    decision: Decision
    actor: str
    authority_source: str
    action: ActionType
    risk: Risk
    ceo_required: bool
    reason: str
    shadow_decision: AuthorityDecision
    gates: tuple[PilotGate, ...] = ()
    escalation_target: str = ""
    integration_branch: str = ""
    authorizes_action: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", assert_record_id(self.request_id, "live.request_id")
        )
        if not isinstance(self.mode, PilotMode):
            raise DelegationError("live.mode must be a PilotMode value")
        if not isinstance(self.decision, Decision):
            raise DelegationError("live.decision must be a Decision value")
        if not isinstance(self.shadow_decision, AuthorityDecision):
            raise DelegationError("live.shadow_decision must be an AuthorityDecision")
        object.__setattr__(self, "reason", assert_prose(self.reason, "live.reason"))
        if not isinstance(self.gates, tuple) or any(
            not isinstance(item, PilotGate) for item in self.gates
        ):
            raise DelegationError("live.gates must be a tuple of PilotGate")
        if not isinstance(self.authorizes_action, bool):
            raise DelegationError("live.authorizes_action must be a boolean")

        # --- the invariants that make this safe to call live ---------------

        if self.authorizes_action:
            if self.mode is not PilotMode.LIVE_PILOT:
                raise PilotBoundaryViolation(
                    "a shadow decision cannot authorize an action; that is what "
                    "shadow means"
                )
            if self.decision is not Decision.APPROVED:
                raise PilotBoundaryViolation(
                    f"a {self.decision.value!r} decision cannot authorize an action"
                )
            if self.ceo_required:
                raise PilotBoundaryViolation(
                    "a decision that requires the CEO cannot authorize itself"
                )
            if self.actor == CEO_SEAT:
                raise PilotBoundaryViolation(
                    "this pilot never writes a CEO approval; reaching the CEO is "
                    "ESCALATE and the approval itself is a named human act"
                )
            if self.actor not in PILOT_SEATS:
                raise PilotBoundaryViolation(
                    f"seat {self.actor!r} holds no live authority in this pilot"
                )
            if self.action not in PILOT_SEATS[self.actor]:
                raise PilotBoundaryViolation(
                    f"seat {self.actor!r} may not live-approve {self.action.value!r}"
                )
            if self.action in PILOT_FORBIDDEN_ACTIONS:
                raise PilotBoundaryViolation(
                    f"{self.action.value!r} is outside this pilot entirely"
                )
            failed = tuple(item.gate_id.value for item in self.gates if not item.held)
            if failed:
                raise PilotBoundaryViolation(
                    "a live approval requires every pilot gate to hold; these did "
                    "not: " + ", ".join(sorted(failed))
                )
            if self.shadow_decision.decision is not Decision.APPROVED:
                raise PilotBoundaryViolation(
                    "the pilot may narrow the shadow answer, never widen it: the "
                    f"shadow calculation said {self.shadow_decision.decision.value!r}"
                )
            if self.shadow_decision.actor != self.actor:
                raise PilotBoundaryViolation(
                    "the pilot may not move the approving seat: the shadow "
                    f"calculation named {self.shadow_decision.actor!r}"
                )
            if self.integration_branch and self.integration_branch in PROTECTED_REFS:
                raise PilotBoundaryViolation(
                    f"no live decision may advance the protected ref "
                    f"{self.integration_branch!r}"
                )
        if self.ceo_required and self.decision is Decision.APPROVED:
            raise PilotBoundaryViolation(
                "a decision cannot both be approved by a delegated seat and require "
                "the CEO; the CEO answer is ESCALATE"
            )

    @property
    def handled_internally(self) -> bool:
        """Decided without the CEO. The number the pilot report counts."""
        return not self.ceo_required and self.decision is not Decision.ESCALATE

    @property
    def failed_gates(self) -> tuple[PilotGate, ...]:
        return tuple(item for item in self.gates if not item.held)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "mode": self.mode.value,
            "decision": self.decision.value,
            "actor": self.actor,
            "authority_source": self.authority_source,
            "action": self.action.value,
            "risk": self.risk.value,
            "ceo_required": self.ceo_required,
            "reason": self.reason,
            "gates": [item.to_dict() for item in self.gates],
            "escalation_target": self.escalation_target,
            "integration_branch": self.integration_branch,
            "authorizes_action": self.authorizes_action,
            "shadow_decision": self.shadow_decision.to_dict(),
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


# --- the gates ------------------------------------------------------------


def _gate(gate_id: PilotGateId, held: bool, detail: str) -> PilotGate:
    return PilotGate(gate_id=gate_id, held=held, detail=detail)


def _integration_gates(
    pilot_request: PilotRequest,
    activation: PilotActivation,
) -> list[PilotGate]:
    """Where the work may land, for the actions that land somewhere."""
    action = pilot_request.action
    target = activation.integration_target
    branch = pilot_request.integration_branch
    gates: list[PilotGate] = []

    if action not in INTEGRATING_ACTIONS:
        return gates

    if branch in PROTECTED_REFS:
        gates.append(
            _gate(
                PilotGateId.PROTECTED_REF,
                False,
                target.refusal(branch),
            )
        )
        return gates
    gates.append(
        _gate(
            PilotGateId.PROTECTED_REF,
            True,
            f"{branch or 'no branch'} is not a protected ref",
        )
    )
    permitted = target.permits(branch)
    gates.append(
        _gate(
            PilotGateId.TARGET_NOT_PERMITTED,
            permitted,
            f"{branch} is this pilot's integration target"
            if permitted
            else target.refusal(branch),
        )
    )

    # The deployment classification has to agree that this is routine, and it is
    # asked about the **kind of act**, not the action name.
    #
    # That distinction matters here. `classification_of(APPROVE_INTEGRATION_MERGE)`
    # is None — the action the policy grants has no row in the deployment table —
    # so keying the gate on the action name would fail closed on every
    # integration and make Phase 5 undemonstrable. The honest question is the
    # one `deployment.py` actually answers: *what sort of deployment is this?*
    # Accepting reviewed work onto a branch that nothing builds on and that is
    # undone by deleting it is a LOCAL_INTEGRATION whatever the action is called,
    # and that kind is routine-delegatable.
    #
    # The kind is derived from the target rather than asserted, so a branch the
    # target does not permit is UNKNOWN and fails closed.
    kind = (
        DeploymentKind.LOCAL_INTEGRATION
        if permitted and target.kind is TargetKind.INTERNAL_BRANCH
        else DeploymentKind.UNKNOWN
    )
    rule = DEPLOYMENT_POLICY.rule(kind)
    classification = rule.classification if rule else None
    routine = classification is DeploymentClass.ROUTINE_DELEGATABLE
    gates.append(
        _gate(
            PilotGateId.DEPLOYMENT_NOT_ROUTINE,
            routine,
            f"{kind.value} is classified "
            + (classification.value if classification else "unclassified")
            + " by deployment.py",
        )
    )
    return gates


def _control_gates(pilot_request: PilotRequest) -> list[PilotGate]:
    """The independent controls a manager may continue past but never override."""
    action = pilot_request.action
    request = pilot_request.request
    gates: list[PilotGate] = []

    # Nobody in this pilot may set aside a failing control, at any risk or
    # amount. The canonical `evaluate` already disqualifies every seat for this;
    # the gate is here so that the *pilot* refusal is visible in the record
    # rather than only the shadow one.
    if request.overrides_independent_control:
        gates.append(
            _gate(
                PilotGateId.QA_NOT_PASSED,
                False,
                "the request would set aside a failing reviewer verdict or QA run, "
                "which no delegated seat may do",
            )
        )
        return gates

    # Approving a review *outcome* requires that a review has run — not that it
    # passed.
    #
    # This distinction is the one the historical replay corrected. Job A's
    # reviewer said `changes_required`, and the routine management act on that
    # verdict is to accept it and authorize a bounded correction. A gate that
    # demanded `review_passed is True` would send every reviewer-found defect to
    # the CEO, which is precisely the behaviour Phase 8 exists to remove.
    #
    # `None` is still refused: it means no review has run, and a manager cannot
    # approve the outcome of a review that has not happened. Approving the
    # verdict is not the same as approving the work, and setting a verdict aside
    # is `overrides_independent_control`, refused above.
    if action is ActionType.APPROVE_REVIEW_OUTCOME:
        reviewed = pilot_request.review_passed is not None
        gates.append(
            _gate(
                PilotGateId.REVIEW_NOT_INDEPENDENT,
                reviewed,
                (
                    "an independent review ran and its verdict was "
                    + ("pass" if pilot_request.review_passed else "changes_required")
                )
                if reviewed
                else (
                    "no independent review is recorded, so there is no outcome to "
                    "approve"
                ),
            )
        )

    # Continuing *to* QA is routine. Continuing *past* a failed QA is not.
    if action is ActionType.APPROVE_TEST_PROGRESSION and pilot_request.qa_passed is False:
        gates.append(
            _gate(
                PilotGateId.QA_NOT_PASSED,
                False,
                "deterministic QA failed; progression past a failing QA run is not "
                "a routine continuation and no pilot seat may approve it",
            )
        )

    # A reviewer may not be the approver. `evaluate` checks this per seat; this
    # restates it as a pilot gate because it is the control the CEO named.
    if request.reviewer and request.reviewer == request.implementer:
        gates.append(
            _gate(
                PilotGateId.REVIEW_NOT_INDEPENDENT,
                False,
                f"{request.reviewer} both implemented and reviewed this work, so no "
                "independent review exists to approve",
            )
        )
    return gates


def _envelope_gates(
    pilot_request: PilotRequest,
    activation: PilotActivation,
    day: dt.date,
) -> list[PilotGate]:
    """The CEO's boundary, checked field by field."""
    envelope = activation.envelope
    request = pilot_request.request
    gates: list[PilotGate] = []

    expired = envelope.expired_on(day)
    gates.append(
        _gate(
            PilotGateId.ENVELOPE_EXPIRED,
            not expired,
            f"the envelope expires {envelope.expires_on.isoformat()} and the "
            f"decision is dated {day.isoformat()}",
        )
    )

    allowed = envelope.permits_action(request.action)
    gates.append(
        _gate(
            PilotGateId.ACTION_NOT_IN_ENVELOPE,
            allowed,
            f"{request.action.value} is in the envelope's allow-list"
            if allowed
            else (
                f"{request.action.value} is not in the envelope's allow-list, which "
                "names only: "
                + ", ".join(item.value for item in envelope.allowed_actions)
            ),
        )
    )

    in_department = envelope.permits_department(request.department)
    gates.append(
        _gate(
            PilotGateId.DEPARTMENT_NOT_IN_ENVELOPE,
            in_department,
            f"{request.department} is an allowed department"
            if in_department
            else (
                f"{request.department} is not in the envelope's departments: "
                + ", ".join(envelope.plan.allowed_departments)
            ),
        )
    )

    in_risk = envelope.permits_risk(request.risk)
    gates.append(
        _gate(
            PilotGateId.RISK_ABOVE_ENVELOPE,
            in_risk,
            f"{request.risk.value} is at or below the envelope ceiling "
            f"{envelope.risk_ceiling.value}",
        )
    )

    in_budget = envelope.permits_amount(request.amount)
    gates.append(
        _gate(
            PilotGateId.AMOUNT_ABOVE_ENVELOPE,
            in_budget,
            "no amount was requested"
            if request.amount is None
            else (
                f"{request.amount.text} against an envelope budget of "
                f"{envelope.budget.text}"
            ),
        )
    )

    # An objective the envelope was not signed for is outside it, even when
    # every ceiling is satisfied. This is the gate that stops one signed
    # envelope from covering the next programme of work.
    if request.objective_id:
        matches = request.objective_id == envelope.objective_id
        gates.append(
            _gate(
                PilotGateId.OBJECTIVE_MISMATCH,
                matches,
                f"the request is under objective {request.objective_id}"
                if matches
                else (
                    f"the request names objective {request.objective_id} and the "
                    f"envelope was signed for {envelope.objective_id}"
                ),
            )
        )

    if pilot_request.corrections_used > envelope.max_corrections_per_work_order:
        gates.append(
            _gate(
                PilotGateId.CORRECTION_CEILING,
                False,
                f"{pilot_request.corrections_used} correction(s) already authorized "
                f"against a ceiling of {envelope.max_corrections_per_work_order}",
            )
        )
    return gates


def _seat_gates(
    pilot_request: PilotRequest,
    shadow: AuthorityDecision,
    policy: DelegationPolicy,
) -> list[PilotGate]:
    """Whether the seat the shadow model chose holds live authority here."""
    action = pilot_request.action
    seat = shadow.actor
    gates: list[PilotGate] = []

    in_pilot = seat in PILOT_SEATS
    gates.append(
        _gate(
            PilotGateId.SEAT_NOT_IN_PILOT,
            in_pilot,
            f"{seat} holds live authority in this pilot"
            if in_pilot
            else (
                f"{seat} holds no live authority in this pilot, which covers only: "
                + ", ".join(sorted(PILOT_SEATS))
            ),
        )
    )
    if not in_pilot:
        return gates

    holds = action in PILOT_SEATS[seat]
    gates.append(
        _gate(
            PilotGateId.ACTION_NOT_IN_PILOT,
            holds,
            f"{seat} may live-approve {action.value}"
            if holds
            else f"{action.value} is not in {seat}'s live action set",
        )
    )

    forbidden = action in PILOT_FORBIDDEN_ACTIONS
    if forbidden:
        gates.append(
            _gate(
                PilotGateId.ACTION_NOT_IN_PILOT,
                False,
                PILOT_FORBIDDEN_REASON.get(
                    action, f"{action.value} is outside this pilot entirely"
                ),
            )
        )

    ceiling = _seat_ceiling(seat, policy)
    within = risk_rank(pilot_request.request.risk) <= risk_rank(ceiling)
    gates.append(
        _gate(
            PilotGateId.RISK_ABOVE_PILOT_CEILING,
            within,
            f"{pilot_request.request.risk.value} is at or below {seat}'s pilot "
            f"ceiling {ceiling.value}"
            if within
            else (
                f"{pilot_request.request.risk.value} is above {seat}'s pilot ceiling "
                f"{ceiling.value}"
            ),
        )
    )
    return gates


def evaluate_live(
    pilot_request: PilotRequest,
    policy: DelegationPolicy,
    *,
    activation: PilotActivation | None = None,
    consumed: Mapping[str, Money] | None = None,
    as_of: dt.date | None = None,
) -> LivePilotDecision:
    """One request, one answer, and whether it may actually proceed.

    With `activation=None` — the default — this is the shadow answer with
    `authorizes_action=False`, exactly as before. That is the whole of Phase 2:
    the default is shadow because the default argument is `None`.

    With an activation, the shadow answer is computed first and then narrowed by
    every pilot gate. The result can be more restrictive than shadow and never
    less.
    """
    if not isinstance(pilot_request, PilotRequest):
        raise DelegationError("evaluate_live expects a PilotRequest")

    shadow = evaluate(pilot_request.request, policy, consumed=consumed)

    if activation is None:
        gate = _gate(
            PilotGateId.NOT_ACTIVATED,
            False,
            "no pilot activation was supplied, so this is the shadow calculation: "
            "it records which seat would be competent and authorizes nothing",
        )
        return LivePilotDecision(
            request_id=shadow.request_id,
            mode=PilotMode.SHADOW,
            decision=shadow.decision,
            actor=shadow.actor,
            authority_source=shadow.authority_source,
            action=shadow.action,
            risk=shadow.risk,
            ceo_required=shadow.ceo_required,
            reason=shadow.reason,
            shadow_decision=shadow,
            gates=(gate,),
            escalation_target=shadow.actor if shadow.escalation_required else "",
            integration_branch=pilot_request.integration_branch,
            authorizes_action=False,
        )

    if not isinstance(activation, PilotActivation):
        raise DelegationError("evaluate_live activation must be a PilotActivation")
    activation.check_against(policy)

    day = as_of or pilot_request.as_of or activation.activated_on
    day = assert_day(day, "evaluate_live.as_of")

    gates: list[PilotGate] = []
    gates.extend(_seat_gates(pilot_request, shadow, policy))
    gates.extend(_envelope_gates(pilot_request, activation, day))
    gates.extend(_control_gates(pilot_request))
    gates.extend(_integration_gates(pilot_request, activation))

    failed = [item for item in gates if not item.held]

    # The floor rule: the pilot may narrow, never widen.
    if shadow.decision is not Decision.APPROVED or shadow.ceo_required:
        return LivePilotDecision(
            request_id=shadow.request_id,
            mode=PilotMode.LIVE_PILOT,
            decision=shadow.decision,
            actor=shadow.actor,
            authority_source=shadow.authority_source,
            action=shadow.action,
            risk=shadow.risk,
            ceo_required=shadow.ceo_required,
            reason=shadow.reason,
            shadow_decision=shadow,
            gates=tuple(gates),
            escalation_target=shadow.actor if shadow.escalation_required else "",
            integration_branch=pilot_request.integration_branch,
            authorizes_action=False,
        )

    if failed:
        first = failed[0]
        return LivePilotDecision(
            request_id=shadow.request_id,
            mode=PilotMode.LIVE_PILOT,
            decision=Decision.ESCALATE,
            actor=CEO_SEAT,
            authority_source=(
                f"pilot gate {first.gate_id.value}: outside the activated envelope"
            ),
            action=shadow.action,
            risk=shadow.risk,
            ceo_required=True,
            reason=(
                f"{shadow.actor} would be competent under the shadow policy, but "
                f"this pilot does not cover it: {first.detail}"
            ),
            shadow_decision=shadow,
            gates=tuple(gates),
            escalation_target=CEO_SEAT,
            integration_branch=pilot_request.integration_branch,
            authorizes_action=False,
        )

    return LivePilotDecision(
        request_id=shadow.request_id,
        mode=PilotMode.LIVE_PILOT,
        decision=Decision.APPROVED,
        actor=shadow.actor,
        authority_source=(
            f"{shadow.authority_source}; live under pilot "
            f"{activation.activation_id} inside envelope {activation.envelope.envelope_id}"
        ),
        action=shadow.action,
        risk=shadow.risk,
        ceo_required=False,
        reason=(
            f"{shadow.actor} holds live authority for {shadow.action.value} at "
            f"{shadow.risk.value} risk inside the activated envelope, and every "
            f"pilot gate held ({len(gates)} checked)"
        ),
        shadow_decision=shadow,
        gates=tuple(gates),
        escalation_target="",
        integration_branch=pilot_request.integration_branch,
        authorizes_action=True,
    )


def evaluate_live_all(
    requests: Sequence[PilotRequest],
    policy: DelegationPolicy,
    *,
    activation: PilotActivation | None = None,
    consumed: Mapping[str, Money] | None = None,
    as_of: dt.date | None = None,
) -> tuple[LivePilotDecision, ...]:
    """`evaluate_live` over a sequence, in order, with no shared state."""
    return tuple(
        evaluate_live(
            item,
            policy,
            activation=activation,
            consumed=consumed,
            as_of=as_of,
        )
        for item in requests
    )


__all__ = [
    "CTO_LIVE_ACTIONS",
    "INTEGRATING_ACTIONS",
    "ENGINEERING_MANAGER_LIVE_ACTIONS",
    "PILOT_FORBIDDEN_ACTIONS",
    "PILOT_FORBIDDEN_REASON",
    "PILOT_RISK_CEILING",
    "PILOT_SEATS",
    "PILOT_VERSION",
    "LivePilotDecision",
    "PilotActivation",
    "PilotGate",
    "PilotGateId",
    "PilotMode",
    "PilotRequest",
    "evaluate_live",
    "evaluate_live_all",
]

"""What "deployment" means, split into five things that need different authority.

The previous phase left a hole and said so: `approve_deployment` was granted to
no seat and reserved by nobody, so a deployment request failed closed to the
CEO as an unclassified escalation. That was correct behaviour and it was not a
policy. This module is the policy, and it still authorizes nothing.

## Why one word had to become five

"Deploy" was doing the work of five unrelated acts with five different blast
radii:

| Kind | What it actually is | Who can undo it |
|---|---|---|
| `LOCAL_INTEGRATION` | merging work into its own branch, running the suite | anyone, immediately |
| `CANONICAL_MERGE` | moving the canonical branch | a revert, with history |
| `STAGING_RELEASE` | an internal build nobody outside sees | delete the build |
| `PUBLIC_DEPLOYMENT` | something the public can reach | not reliably |
| `CONTENT_PUBLISHING` | a video on the channel | not at all — it has been seen |

Classifying them together meant either blocking the harmless one or permitting
the irreversible one. They are now separate action types with separate
classifications.

## The three classifications

`ROUTINE_DELEGATABLE` — could be delegated to management **once delegation is
activated**. Today it is not, and `DEPLOYMENT_POLICY.activated` is `False`.

`EXECUTIVE_APPROVAL` — an executive seat within its ceiling, never a worker.

`CEO_RESERVED` — the CEO, whatever the risk and whatever the amount. Public
deployment and content publishing are here because reversibility is the
property that decides it, and neither has any.

## Why `UNKNOWN` exists and is reserved

A deployment kind this module does not recognise is `UNKNOWN`, and `UNKNOWN` is
`CEO_RESERVED`. That is the fail-closed rule the brief asks for, and it is a
member of the enum rather than a fallback branch so that it appears in the
policy table a reader checks, and so that `classify` has no default arm that
could quietly acquire a laxer answer.

## Why nothing here is activated

`DeploymentPolicy.activated` refuses to be `True`. Every classification carries
`authorized=False`. This module describes which authority *would* be required;
granting it is `change_delegation_policy`, which `company/delegation/actions.py`
reserves to the CEO unconditionally.

`company/delegation_policy.yaml` grants none of the deployment action types to
any seat, and a test asserts that. So the model can be read, argued with and
changed in a diff, and none of it can be exercised.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .actions import ActionType
from .errors import DelegationError, ShadowModeViolation


POLICY_VERSION = "deployment_policy_v1"


class DeploymentKind(str, Enum):
    """The five acts one word used to cover, plus the fail-closed sixth."""

    LOCAL_INTEGRATION = "local_integration"
    CANONICAL_MERGE = "canonical_merge"
    STAGING_RELEASE = "staging_release"
    PUBLIC_DEPLOYMENT = "public_deployment"
    CONTENT_PUBLISHING = "content_publishing"
    UNKNOWN = "unknown"


class DeploymentClass(str, Enum):
    """How much authority a kind needs. Three levels, no scores."""

    ROUTINE_DELEGATABLE = "routine_delegatable"
    EXECUTIVE_APPROVAL = "executive_approval"
    CEO_RESERVED = "ceo_reserved"


@dataclass(frozen=True)
class DeploymentRule:
    """One kind, its classification, the action that carries it, and why."""

    kind: DeploymentKind
    classification: DeploymentClass
    action: ActionType
    reversible: bool
    rationale: str
    reserved_as: str = ""  # the permissions.yaml name, when there is one

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "classification": self.classification.value,
            "action": self.action.value,
            "reversible": self.reversible,
            "rationale": self.rationale,
            "reserved_as": self.reserved_as,
        }


RULES: tuple[DeploymentRule, ...] = (
    DeploymentRule(
        kind=DeploymentKind.LOCAL_INTEGRATION,
        classification=DeploymentClass.ROUTINE_DELEGATABLE,
        action=ActionType.APPROVE_LOCAL_INTEGRATION,
        reversible=True,
        rationale=(
            "merging reviewed work into its own branch and running the suite changes "
            "nothing anybody else can see, and is undone by deleting a branch"
        ),
    ),
    DeploymentRule(
        kind=DeploymentKind.CANONICAL_MERGE,
        classification=DeploymentClass.EXECUTIVE_APPROVAL,
        action=ActionType.APPROVE_CANONICAL_MERGE,
        reversible=True,
        rationale=(
            "moving the canonical branch is reversible by a revert, but everything "
            "downstream builds on it from that moment, so it is an executive call"
        ),
    ),
    DeploymentRule(
        kind=DeploymentKind.STAGING_RELEASE,
        classification=DeploymentClass.EXECUTIVE_APPROVAL,
        action=ActionType.APPROVE_STAGING_RELEASE,
        reversible=True,
        rationale=(
            "an internal build reaches people inside the company and nobody outside; "
            "deleting it undoes it"
        ),
    ),
    DeploymentRule(
        kind=DeploymentKind.PUBLIC_DEPLOYMENT,
        classification=DeploymentClass.CEO_RESERVED,
        action=ActionType.APPROVE_DEPLOYMENT,
        reversible=False,
        rationale=(
            "once the public can reach it, taking it down does not unmake the fact "
            "that it was reachable"
        ),
    ),
    DeploymentRule(
        kind=DeploymentKind.CONTENT_PUBLISHING,
        classification=DeploymentClass.CEO_RESERVED,
        action=ActionType.PUBLISH_PUBLIC_VIDEO,
        reversible=False,
        rationale=(
            "a published video has been seen; company/permissions.yaml already "
            "reserves this and the classification follows that file"
        ),
        reserved_as="publish_public_video",
    ),
    DeploymentRule(
        kind=DeploymentKind.UNKNOWN,
        classification=DeploymentClass.CEO_RESERVED,
        action=ActionType.APPROVE_DEPLOYMENT,
        reversible=False,
        rationale=(
            "a deployment nobody classified has no measured blast radius, so it is "
            "treated as the largest one rather than the smallest"
        ),
    ),
)


@dataclass(frozen=True)
class DeploymentDecision:
    """What a deployment request would need. Never what it may do."""

    kind: DeploymentKind
    classification: DeploymentClass
    action: ActionType
    reversible: bool
    rationale: str
    ceo_required: bool
    reserved_as: str = ""
    authorized: bool = False
    activated: bool = False

    def __post_init__(self) -> None:
        if self.authorized is not False or self.activated is not False:
            raise ShadowModeViolation(
                "a deployment decision authorizes nothing in this version. The policy "
                "says which authority would be required; granting it is "
                "change_delegation_policy, which is CEO-reserved."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "classification": self.classification.value,
            "action": self.action.value,
            "reversible": self.reversible,
            "rationale": self.rationale,
            "ceo_required": self.ceo_required,
            "reserved_as": self.reserved_as,
            "authorized": False,
            "activated": False,
        }


@dataclass(frozen=True)
class DeploymentPolicy:
    """The rule table, and the switch that is off."""

    rules: tuple[DeploymentRule, ...] = RULES
    version: str = POLICY_VERSION
    activated: bool = False

    def __post_init__(self) -> None:
        if self.activated is not False:
            raise ShadowModeViolation(
                "deployment authority is not activated in this version. Building the "
                "policy model and granting authority under it are two separate CEO "
                "decisions, and only the first has been taken."
            )
        by_kind: dict[DeploymentKind, DeploymentRule] = {}
        for rule in self.rules:
            if not isinstance(rule, DeploymentRule):
                raise DelegationError("every deployment rule must be a DeploymentRule")
            if rule.kind in by_kind:
                raise DelegationError(f"deployment kind {rule.kind.value} is ruled twice")
            by_kind[rule.kind] = rule
        missing = sorted(
            kind.value for kind in DeploymentKind if kind not in by_kind
        )
        if missing:
            raise DelegationError(
                "the deployment policy does not classify: "
                + ", ".join(missing)
                + ". An unclassified kind would take whatever the default arm gives "
                "it, which is how a fail-closed rule stops failing closed."
            )
        object.__setattr__(self, "_by_kind", by_kind)

    @property
    def _index(self) -> dict[DeploymentKind, DeploymentRule]:
        return getattr(self, "_by_kind")

    def rule(self, kind: DeploymentKind) -> DeploymentRule:
        return self._index[kind]

    def classify(self, kind: Any) -> DeploymentDecision:
        """What this deployment kind would need. An unknown name becomes UNKNOWN."""
        resolved = parse_kind(kind, allow_unknown=True)
        rule = self._index[resolved]
        return DeploymentDecision(
            kind=rule.kind,
            classification=rule.classification,
            action=rule.action,
            reversible=rule.reversible,
            rationale=rule.rationale,
            ceo_required=rule.classification is DeploymentClass.CEO_RESERVED,
            reserved_as=rule.reserved_as,
        )

    def actions(self) -> frozenset[ActionType]:
        """Every action type the deployment policy names."""
        return frozenset(rule.action for rule in self.rules)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "activated": False,
            "rules": [rule.to_dict() for rule in self.rules],
        }


def parse_kind(value: Any, *, allow_unknown: bool = False) -> DeploymentKind:
    """Decode a deployment kind.

    With `allow_unknown`, an unrecognised name becomes `UNKNOWN` — which is
    CEO-reserved, so an unfamiliar deployment is treated as the largest one
    rather than refused outright. Without it, an unrecognised name raises,
    which is what a stored record wants.
    """
    if isinstance(value, DeploymentKind):
        return value
    if not isinstance(value, str) or not value.strip():
        if allow_unknown:
            return DeploymentKind.UNKNOWN
        raise DelegationError(f"deployment kind must be a name, got {value!r}")
    try:
        return DeploymentKind(value.strip().lower())
    except ValueError:
        if allow_unknown:
            return DeploymentKind.UNKNOWN
        allowed = ", ".join(item.value for item in DeploymentKind)
        raise DelegationError(
            f"deployment kind {value!r} is not one of: {allowed}"
        ) from None


DEPLOYMENT_POLICY = DeploymentPolicy()

# The action types the deployment policy covers, for the delegation policy to
# check against. None of them is granted to any seat in this version.
DEPLOYMENT_ACTIONS: frozenset[ActionType] = DEPLOYMENT_POLICY.actions()


def classification_of(action: ActionType) -> DeploymentClass | None:
    """The strictest classification any rule gives this action, or None.

    `APPROVE_DEPLOYMENT` carries both `PUBLIC_DEPLOYMENT` and `UNKNOWN`, and
    both are CEO-reserved, so "strictest" is well defined and does not depend on
    rule order.
    """
    found = [
        rule.classification for rule in DEPLOYMENT_POLICY.rules if rule.action is action
    ]
    if not found:
        return None
    order = {
        DeploymentClass.ROUTINE_DELEGATABLE: 0,
        DeploymentClass.EXECUTIVE_APPROVAL: 1,
        DeploymentClass.CEO_RESERVED: 2,
    }
    return max(found, key=lambda item: order[item])


def policy_table(policy: Mapping[str, Any] | None = None) -> str:
    """The rule table as text, for a report or a terminal."""
    lines = [
        f"DEPLOYMENT POLICY {POLICY_VERSION} — activated: false",
        "",
        f"  {'kind':<20} {'classification':<22} {'reversible':<11} action",
    ]
    for rule in DEPLOYMENT_POLICY.rules:
        lines.append(
            f"  {rule.kind.value:<20} {rule.classification.value:<22} "
            f"{str(rule.reversible).lower():<11} {rule.action.value}"
        )
    return "\n".join(lines)


__all__ = [
    "DEPLOYMENT_ACTIONS",
    "DEPLOYMENT_POLICY",
    "POLICY_VERSION",
    "RULES",
    "DeploymentClass",
    "DeploymentDecision",
    "DeploymentKind",
    "DeploymentPolicy",
    "DeploymentRule",
    "classification_of",
    "parse_kind",
    "policy_table",
]

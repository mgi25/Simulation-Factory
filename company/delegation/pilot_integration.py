"""Where delegated work may be accepted, and the branches it may never touch.

## Why this module exists at all

The delegation model already classifies *deployment* (`deployment.py`): five
kinds, from a local integration nobody can see to a video the public has
already watched. What it never had was a **named place**. "Local integration is
routine-delegatable" is a statement about a class of act; it does not say which
branch a manager may accept work onto, and a pilot that leaves that blank is a
pilot that permits `main` by omission.

So this module supplies the missing noun. An `IntegrationTarget` is the one
branch a live-pilot decision may name, and `PROTECTED_REFS` is the set it may
never name whatever the policy, the envelope or the seat says.

## Why the protected set is a constant and not configuration

Everything else in this package is loaded from YAML so the CEO can change it
without a code change. This is deliberately the opposite. A configurable
protected-branch list is a protected-branch list that a future policy edit can
empty, and the whole value of the guard is that it cannot be argued with.
Adding a branch here is a source change, a review and a test — which is the
correct weight for "the pilot may now write to this".

`main` is on it because the CEO said so. `company-os-v1-bootstrap` is on it
because it is canonical: moving it is `approve_canonical_merge`, which
`deployment.py` already classifies as EXECUTIVE_APPROVAL rather than routine,
and which this pilot does not grant to anybody.

## What this module cannot do

It cannot merge. Nothing here runs git, opens a socket or spawns a process —
`tests/test_company_delegation_pilot.py` asserts that against the source, the
same way `production.no_publishing_capability` asserts it against every Company
OS module. An `IntegrationTarget` is a *name a decision carries*, and the act
of integrating remains outside this package entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .common import assert_prose, assert_record_id
from .errors import DelegationError, PilotBoundaryViolation


# Refs a delegated decision may never name as its integration target, at any
# risk, any amount and any seat. See the module docstring for why this is a
# constant.
PROTECTED_REFS: frozenset[str] = frozenset(
    {
        "main",
        "master",
        "company-os-v1-bootstrap",
    }
)

# Why each one is protected, so a refusal can say something better than "no".
PROTECTED_REASON: dict[str, str] = {
    "main": (
        "main is the production branch; moving it is a public-facing act and the "
        "CEO reserved it for this pilot explicitly"
    ),
    "master": (
        "the legacy name for the production branch, protected so that a rename "
        "cannot quietly open a door this pilot closed"
    ),
    "company-os-v1-bootstrap": (
        "the canonical Company OS branch; moving it is approve_canonical_merge, "
        "which deployment.py classifies as executive rather than routine"
    ),
}


class TargetKind(str, Enum):
    """What sort of place work is being accepted into."""

    # A branch that exists for one pilot and nothing downstream builds on.
    INTERNAL_BRANCH = "internal_branch"
    # Anything else. Present so that an unclassified target fails closed rather
    # than defaulting to the harmless answer.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntegrationTarget:
    """The one branch this pilot may accept work onto, and its guarantees."""

    target_id: str
    kind: TargetKind
    branch: str
    rationale: str
    # True when deleting the branch undoes the integration completely. A target
    # that is not reversible is not an internal integration target, whatever it
    # is called, and the pilot refuses it.
    reversible: bool = True
    # Refs this target promises never to advance. Always a superset of
    # PROTECTED_REFS; a target may add to the set but never subtract from it.
    protects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "target_id", assert_record_id(self.target_id, "target.target_id")
        )
        if not isinstance(self.kind, TargetKind):
            raise DelegationError("target.kind must be a TargetKind value")
        branch = assert_prose(self.branch, "target.branch")
        if any(ch.isspace() for ch in branch):
            raise DelegationError(
                f"target.branch {branch!r} contains whitespace; a branch name does not"
            )
        object.__setattr__(self, "branch", branch)
        object.__setattr__(
            self, "rationale", assert_prose(self.rationale, "target.rationale")
        )
        if not isinstance(self.reversible, bool):
            raise DelegationError("target.reversible must be a boolean")

        if self.kind is not TargetKind.INTERNAL_BRANCH:
            raise PilotBoundaryViolation(
                f"target {self.target_id!r} has kind {self.kind.value!r}. This pilot "
                "accepts work onto an internal branch and nothing else; an "
                "unclassified target fails closed rather than being assumed harmless."
            )
        if not self.reversible:
            raise PilotBoundaryViolation(
                f"target {self.target_id!r} declares itself irreversible. An internal "
                "integration target is undone by deleting the branch; one that is not "
                "is a release, and a release is not delegated by this pilot."
            )
        if branch in PROTECTED_REFS:
            raise PilotBoundaryViolation(
                f"target {self.target_id!r} names the protected ref {branch!r}: "
                f"{PROTECTED_REASON[branch]}. No envelope, grant or seat can permit "
                "this; widening it is a source change and a CEO decision."
            )

        declared = tuple(
            assert_prose(item, "target.protects") for item in (self.protects or ())
        )
        merged = tuple(sorted(set(declared) | PROTECTED_REFS))
        object.__setattr__(self, "protects", merged)

    def permits(self, branch: Any) -> bool:
        """True when this target may accept work onto `branch`."""
        name = str(branch or "").strip()
        if not name or name in self.protects:
            return False
        return name == self.branch

    def refusal(self, branch: Any) -> str:
        """Why `permits` said no, in words a CEO report can quote."""
        name = str(branch or "").strip()
        if not name:
            return "no integration branch was named, so nothing was checked"
        if name in PROTECTED_REFS:
            return f"{name} is protected: {PROTECTED_REASON[name]}"
        if name in self.protects:
            return (
                f"{name} is protected by integration target {self.target_id!r}, which "
                "promised not to advance it"
            )
        if name != self.branch:
            return (
                f"{name} is not this pilot's integration target; the pilot was "
                f"activated for {self.branch!r} only"
            )
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "kind": self.kind.value,
            "branch": self.branch,
            "rationale": self.rationale,
            "reversible": self.reversible,
            "protects": list(self.protects),
        }


# The target this pilot ships with. A branch that exists for the pilot, that
# nothing builds on, and that is undone by `git branch -D`.
PILOT_TARGET = IntegrationTarget(
    target_id="pilot-internal-integration",
    kind=TargetKind.INTERNAL_BRANCH,
    branch="company-os-v1-delegated-engineering-pilot-integration",
    rationale=(
        "an internal branch created for this pilot, which no other branch builds "
        "on and which is undone completely by deleting it, so that work can be "
        "completed and accepted internally without anything leaving the company"
    ),
)


__all__ = [
    "PILOT_TARGET",
    "PROTECTED_REASON",
    "PROTECTED_REFS",
    "IntegrationTarget",
    "TargetKind",
]

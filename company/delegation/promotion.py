"""Where routine engineering work may land, and the line it may not cross.

Two destinations, and the whole value of this module is that they are not the
same thing:

    INTERNAL ENGINEERING INTEGRATION
        Completed, reviewed, QA-green work lands on one internal engineering
        branch. The CTO may authorize this inside a bounded objective without
        the CEO. It is reversible by deleting a branch, it ships nothing, and
        nobody outside the company sees it.

    CANONICAL / PRODUCTION PROMOTION
        Moving that work onto `company-os-v1-bootstrap`, `main` or anything
        public. **This module grants no path to it.** There is no seat, no
        ceiling and no contract shape in bounded routine engineering that
        reaches it.

## Why the boundary is a module and not a convention

The successful pilot integrated into an isolated branch because the pilot
envelope named one. Turning that into the normal operating mode means the
destination stops being a property of one envelope and becomes a property of
the company, and a destination that lives in configuration is a destination a
configuration edit can move.

So the internal target is a constant here, `PROTECTED_REFS` stays a constant in
`pilot_integration.py`, and both are source changes with tests attached.

## What makes internally integrated work eligible for release later

Nothing automatic, and deliberately so. Work that reaches
`ObjectiveState.INTERNALLY_INTEGRATED` is *eligible to be proposed* for
promotion and nothing more. A promotion is:

1. a separate CEO decision, at program or release level rather than per change;
2. over a *batch* of internally integrated work, not one commit;
3. gated on the production integration gate reporting READY with no blockers;
4. executed by the same fast-forward discipline canonical already uses.

That capability is not implemented here. `promotion_readiness` answers only
"would this be a sane thing to propose", so that the eventual capability has
something honest to read, and so a CEO looking at an internally integrated
objective can see what promotion *would* require.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .common import assert_prose
from .errors import DelegationError
from .pilot_integration import PROTECTED_REFS, IntegrationTarget, TargetKind


PROMOTION_VERSION = "promotion_boundary_v1"


#: The one branch routine bounded engineering may accept work onto.
#:
#: One branch, not one per objective: branch sprawl makes the question "what
#: has the company actually built" unanswerable, which is the question this
#: whole layer exists to keep answerable. Objectives are separated by their
#: records, not by their refs.
INTERNAL_ENGINEERING_TARGET = "company-os-v1-engineering-integration"

#: Refs that routine engineering may never advance, whatever any contract,
#: seat or ceiling says. A superset of `PROTECTED_REFS`, never a subset.
NEVER_ADVANCED: frozenset[str] = frozenset(PROTECTED_REFS) | frozenset(
    {
        # Named explicitly rather than pattern-matched: a pattern is something
        # a future branch name can slip past.
        "release",
        "production",
        "gh-pages",
    }
)


#: The same branch as an `IntegrationTarget`, which is the shape `evaluate_live`
#: checks an integration request against. Declared once here so the production
#: envelope and this module cannot disagree about where work goes.
INTERNAL_ENGINEERING_TARGET_SPEC = IntegrationTarget(
    target_id="internal-engineering-integration",
    kind=TargetKind.INTERNAL_BRANCH,
    branch=INTERNAL_ENGINEERING_TARGET,
    rationale=(
        "the one internal branch routine bounded engineering accepts work onto. "
        "Nothing downstream builds on it, deleting it undoes every integration "
        "completely, and nothing is released or published by landing here"
    ),
    protects=tuple(sorted(NEVER_ADVANCED)),
)


class Destination(str, Enum):
    """What kind of place a piece of work is being asked to land."""

    INTERNAL_ENGINEERING = "internal_engineering"
    CANONICAL = "canonical"
    PUBLIC = "public"
    UNKNOWN = "unknown"


def classify_destination(branch: str) -> Destination:
    """What kind of destination this ref is. Fails towards UNKNOWN, not towards
    permission: an unrecognised ref is never internal engineering."""
    ref = assert_prose(branch, "branch").strip()
    if ref == INTERNAL_ENGINEERING_TARGET:
        return Destination.INTERNAL_ENGINEERING
    if ref in {"company-os-v1-bootstrap"}:
        return Destination.CANONICAL
    if ref in NEVER_ADVANCED:
        return Destination.PUBLIC
    return Destination.UNKNOWN


@dataclass(frozen=True)
class IntegrationVerdict:
    """Whether routine engineering may land work here, and why not when not."""

    branch: str
    destination: Destination
    permitted: bool
    reason: str
    ceo_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "destination": self.destination.value,
            "permitted": self.permitted,
            "reason": self.reason,
            "ceo_required": self.ceo_required,
        }


def may_integrate(branch: str) -> IntegrationVerdict:
    """The routine-engineering answer for one destination.

    This runs *before* `evaluate_live` sees an integration request and answers
    a narrower question: is this the kind of place routine work goes at all.
    `evaluate_live` still applies the protected-ref gate afterwards, so the
    guarantee does not rest on this function being called.
    """
    destination = classify_destination(branch)
    if destination is Destination.INTERNAL_ENGINEERING:
        return IntegrationVerdict(
            branch=branch,
            destination=destination,
            permitted=True,
            reason=(
                f"{INTERNAL_ENGINEERING_TARGET} is the internal engineering "
                "integration target; nothing is released and nothing is published "
                "by landing here"
            ),
        )
    if destination is Destination.CANONICAL:
        return IntegrationVerdict(
            branch=branch,
            destination=destination,
            permitted=False,
            ceo_required=True,
            reason=(
                "moving canonical is promotion, not routine engineering. Bounded "
                "routine engineering grants no path to it: the CEO promotes a "
                "batch of internally integrated work at release level, which is a "
                "separate capability this mode does not implement."
            ),
        )
    if destination is Destination.PUBLIC:
        return IntegrationVerdict(
            branch=branch,
            destination=destination,
            permitted=False,
            ceo_required=True,
            reason=(
                f"{branch} is a public or production ref and is never advanced by "
                "a delegated decision"
            ),
        )
    return IntegrationVerdict(
        branch=branch,
        destination=destination,
        permitted=False,
        ceo_required=True,
        reason=(
            f"{branch} is not the internal engineering target. An unrecognised "
            "destination is refused rather than guessed at, because guessing here "
            "is how work reaches somewhere nobody authorized."
        ),
    )


@dataclass(frozen=True)
class PromotionReadiness:
    """What promoting this internally integrated work *would* require.

    Advisory. Nothing in this module promotes anything, and a `ready` of True
    means only that a promotion proposal would not be obviously unfounded.
    """

    objective_ids: tuple[str, ...]
    internally_integrated: bool
    gate_ready: bool
    blockers: tuple[str, ...]
    ready: bool
    reason: str
    requires: tuple[str, ...] = (
        "a CEO decision at release or program level, not per change",
        "a batch of internally integrated work rather than one commit",
        "the production integration gate READY with zero blockers",
        "a fast-forward onto canonical, no force, no squash, no merge commit",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective_ids": list(self.objective_ids),
            "internally_integrated": self.internally_integrated,
            "gate_ready": self.gate_ready,
            "blockers": list(self.blockers),
            "ready": self.ready,
            "reason": self.reason,
            "requires": list(self.requires),
            "version": PROMOTION_VERSION,
        }


def promotion_readiness(
    objective_ids: Sequence[str],
    *,
    internally_integrated: bool,
    gate_ready: bool,
    blockers: Sequence[str] = (),
) -> PromotionReadiness:
    """Whether a promotion proposal would be sane. It authorizes nothing."""
    ids = tuple(str(item) for item in objective_ids)
    if not ids:
        raise DelegationError("promotion_readiness needs at least one objective")
    found = tuple(str(item) for item in blockers)
    ready = bool(internally_integrated and gate_ready and not found)
    if ready:
        reason = (
            f"{len(ids)} objective(s) are internally integrated and the gate is "
            "READY with no blockers. This is a candidate for a CEO promotion "
            "decision; it is not a promotion and nothing has moved."
        )
    elif not internally_integrated:
        reason = "the work is not on the internal engineering target yet"
    elif not gate_ready:
        reason = "the production integration gate does not report READY"
    else:
        reason = "the gate reports blockers: " + ", ".join(found)
    return PromotionReadiness(
        objective_ids=ids,
        internally_integrated=bool(internally_integrated),
        gate_ready=bool(gate_ready),
        blockers=found,
        ready=ready,
        reason=reason,
    )


__all__ = [
    "INTERNAL_ENGINEERING_TARGET",
    "INTERNAL_ENGINEERING_TARGET_SPEC",
    "NEVER_ADVANCED",
    "PROMOTION_VERSION",
    "Destination",
    "IntegrationVerdict",
    "PromotionReadiness",
    "classify_destination",
    "may_integrate",
    "promotion_readiness",
]

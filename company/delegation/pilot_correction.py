"""One bounded correction, authorized by a manager, counted against a ceiling.

## The behaviour this exists for

    developer
      -> independent reviewer says changes_required
      -> Engineering Manager authorizes ONE bounded correction
      -> corrected implementation
      -> independent reviewer
      -> deterministic QA
      -> management approval

The CEO should not be involved because the first attempt had an ordinary,
fixable defect. That is a normal engineering morning, not an exception. But
"the manager may authorize a correction" without a ceiling is an unbounded
retry loop with a manager's name on it, and an unbounded retry loop on a metered
provider is how a consumer subscription is spent overnight.

## Where the ceiling comes from, and the surprise in it

`company/efficiency/profile.py` already holds the answer, and it is stricter
than it looks:

    CONSUMER.developer_attempts = 1
    CONSUMER.auto_continue_after_changes_required = False

`developer_attempts = 1` means a work order gets **one** developer session.
There is no second attempt on the same work order to authorize. So the bounded
correction the CEO described is not a retry — it is a **new, bounded work
order**, which is exactly how the burn-in phase actually did it
(`burnin-correction` in `scenarios.py` is a second work order, not a second
attempt). This module counts those, per parent work order.

`auto_continue_after_changes_required = False` is the second constraint, and it
is the one worth reading twice. The consumer profile says continuation after
`changes_required` is **not automatic**. This pilot does not change that flag
and does not route around it. What it changes is *who supplies the non-automatic
decision*: in shadow that was the CEO, and in the pilot it is the Engineering
Manager, who must make an explicit, recorded, counted authorization. A flag that
says "not automatic" is satisfied by a named human seat deciding; it would not
be satisfied by this module deciding on its own, which is why
`authorize_correction` refuses to produce an authorization without one.

## Why the ledger is passed in rather than read from disk

A correction count that this module discovered for itself would be a count this
module could be wrong about. The caller owns the history — it is the same
caller that owns the work orders — and passes what it knows. The ledger is
immutable: authorizing a correction returns a new one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from company.efficiency.profile import PROFILES, ResourceProfile, ResourceProfileName

from .actions import ActionType
from .common import assert_prose, assert_record_id
from .errors import DelegationError, PilotBoundaryViolation
from .pilot import PILOT_SEATS, PilotActivation


# The seats that may authorize a bounded correction. Narrower than the pilot
# seat set on purpose: an integration decision is not a correction.
CORRECTION_SEATS: frozenset[str] = frozenset({"engineering_manager", "cto"})


@dataclass(frozen=True)
class CorrectionLedger:
    """How many bounded corrections each work order has already had.

    Immutable. `authorize` returns a new ledger rather than mutating this one,
    so a refused authorization cannot leave a count incremented behind it.
    """

    counts: Mapping[str, int]

    def __post_init__(self) -> None:
        raw = dict(self.counts or {})
        clean: dict[str, int] = {}
        for key, value in raw.items():
            work_order = assert_record_id(key, "ledger.work_order_id")
            if isinstance(value, bool) or not isinstance(value, int):
                raise DelegationError(
                    f"ledger[{work_order}] must be an integer, not {value!r}"
                )
            if value < 0:
                raise DelegationError(f"ledger[{work_order}] is not negative")
            clean[work_order] = value
        object.__setattr__(self, "counts", dict(sorted(clean.items())))

    @classmethod
    def empty(cls) -> CorrectionLedger:
        return cls(counts={})

    def used(self, work_order_id: str) -> int:
        return int(self.counts.get(work_order_id, 0))

    def with_correction(self, work_order_id: str) -> CorrectionLedger:
        key = assert_record_id(work_order_id, "ledger.work_order_id")
        updated = dict(self.counts)
        updated[key] = updated.get(key, 0) + 1
        return CorrectionLedger(counts=updated)

    def to_dict(self) -> dict[str, Any]:
        return {"counts": dict(self.counts)}


@dataclass(frozen=True)
class CorrectionVerdict:
    """Whether one more bounded correction may be authorized, and by whom."""

    work_order_id: str
    permitted: bool
    used: int
    ceiling: int
    reason: str
    authorizing_seat: str = ""
    ceo_required: bool = False
    # The ledger as it stands after this verdict. Unchanged when refused.
    ledger: CorrectionLedger = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "work_order_id",
            assert_record_id(self.work_order_id, "verdict.work_order_id"),
        )
        object.__setattr__(self, "reason", assert_prose(self.reason, "verdict.reason"))
        for flag in ("permitted", "ceo_required"):
            if not isinstance(getattr(self, flag), bool):
                raise DelegationError(f"verdict.{flag} must be a boolean")
        if self.ledger is None:
            object.__setattr__(self, "ledger", CorrectionLedger.empty())
        if self.permitted and self.ceo_required:
            raise PilotBoundaryViolation(
                "a correction cannot be both permitted below the CEO and require "
                "the CEO"
            )
        if self.permitted and not self.authorizing_seat:
            raise PilotBoundaryViolation(
                "a permitted correction must name the seat that authorized it; an "
                "unattributed authorization is not an authorization"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_order_id": self.work_order_id,
            "permitted": self.permitted,
            "used": self.used,
            "ceiling": self.ceiling,
            "reason": self.reason,
            "authorizing_seat": self.authorizing_seat,
            "ceo_required": self.ceo_required,
            "ledger": self.ledger.to_dict(),
        }


def correction_ceiling(
    activation: PilotActivation,
    profile: ResourceProfile | None = None,
) -> int:
    """The number of bounded corrections permitted, from the stricter source.

    The CEO's envelope and the resource profile both have an opinion, and the
    lower one wins. Neither can widen the other: an envelope asking for three
    corrections on a consumer subscription gets the consumer answer, and a
    generous profile does not override a CEO who asked for one.
    """
    resolved = profile or PROFILES[ResourceProfileName.CONSUMER]
    # A work order gets `developer_attempts` sessions in total. The first is the
    # original implementation, so the corrections available beyond it are one
    # fewer — but the correction this pilot authorizes is a *new bounded work
    # order* (see the module docstring), which gets its own attempt allowance.
    # The profile's constraint on that is `reviewer_passes`: a correction that
    # cannot be independently reviewed again is not a correction this pilot
    # permits, because the re-review is the thing that makes it safe.
    by_profile = max(0, int(resolved.reviewer_passes))
    by_envelope = int(activation.envelope.max_corrections_per_work_order)
    return min(by_profile, by_envelope)


def authorize_correction(
    work_order_id: str,
    *,
    activation: PilotActivation,
    authorizing_seat: str,
    reviewer_said_changes_required: bool,
    ledger: CorrectionLedger | None = None,
    profile: ResourceProfile | None = None,
) -> CorrectionVerdict:
    """Decide whether one more bounded correction may proceed without the CEO.

    Refuses rather than raises for the ordinary "no": a work order that has
    used its corrections is a normal state that the CEO should hear about, not
    a programming error.
    """
    if not isinstance(activation, PilotActivation):
        raise DelegationError("authorize_correction expects a PilotActivation")
    work_order_id = assert_record_id(work_order_id, "correction.work_order_id")
    current = ledger or CorrectionLedger.empty()
    used = current.used(work_order_id)
    ceiling = correction_ceiling(activation, profile)

    if not reviewer_said_changes_required:
        return CorrectionVerdict(
            work_order_id=work_order_id,
            permitted=False,
            used=used,
            ceiling=ceiling,
            reason=(
                "no reviewer asked for changes, so there is nothing to correct; a "
                "correction authorized without a reviewer verdict is a second "
                "attempt at the same work, which the resource profile does not fund"
            ),
            ledger=current,
        )

    if authorizing_seat not in CORRECTION_SEATS:
        return CorrectionVerdict(
            work_order_id=work_order_id,
            permitted=False,
            used=used,
            ceiling=ceiling,
            reason=(
                f"{authorizing_seat} may not authorize a bounded correction; only "
                + ", ".join(sorted(CORRECTION_SEATS))
                + " hold that authority in this pilot"
            ),
            ceo_required=True,
            ledger=current,
        )
    if authorizing_seat not in PILOT_SEATS:
        return CorrectionVerdict(
            work_order_id=work_order_id,
            permitted=False,
            used=used,
            ceiling=ceiling,
            reason=f"{authorizing_seat} holds no live authority in this pilot",
            ceo_required=True,
            ledger=current,
        )
    if ActionType.REQUEST_BOUNDED_CORRECTION not in PILOT_SEATS[authorizing_seat]:
        return CorrectionVerdict(
            work_order_id=work_order_id,
            permitted=False,
            used=used,
            ceiling=ceiling,
            reason=(
                f"{authorizing_seat}'s live action set does not include "
                "request_bounded_correction"
            ),
            ceo_required=True,
            ledger=current,
        )
    if not activation.envelope.permits_action(ActionType.REQUEST_BOUNDED_CORRECTION):
        return CorrectionVerdict(
            work_order_id=work_order_id,
            permitted=False,
            used=used,
            ceiling=ceiling,
            reason=(
                "the activated envelope does not allow request_bounded_correction, "
                "so a correction is outside what the CEO signed for"
            ),
            ceo_required=True,
            ledger=current,
        )

    if used >= ceiling:
        return CorrectionVerdict(
            work_order_id=work_order_id,
            permitted=False,
            used=used,
            ceiling=ceiling,
            reason=(
                f"{used} bounded correction(s) already authorized against a ceiling "
                f"of {ceiling}. The ceiling is the lower of the CEO envelope "
                f"({activation.envelope.max_corrections_per_work_order}) and the "
                "resource profile. A further attempt is exceptional spend and is "
                "the CEO's call."
            ),
            ceo_required=True,
            ledger=current,
        )

    return CorrectionVerdict(
        work_order_id=work_order_id,
        permitted=True,
        used=used + 1,
        ceiling=ceiling,
        reason=(
            f"{authorizing_seat} authorized bounded correction {used + 1} of "
            f"{ceiling} after an independent reviewer asked for changes; the "
            "corrected work is independently reviewed again before approval"
        ),
        authorizing_seat=authorizing_seat,
        ceo_required=False,
        ledger=current.with_correction(work_order_id),
    )


__all__ = [
    "CORRECTION_SEATS",
    "CorrectionLedger",
    "CorrectionVerdict",
    "authorize_correction",
    "correction_ceiling",
]

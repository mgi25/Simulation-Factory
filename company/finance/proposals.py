"""Asking to spend money, and the four things asking is not.

Finance does not execute payment. It does not create a subscription. It does not
change a permission. It does not approve itself. Section 12 lists all four, and
this module is where they are structural rather than promised: there is no
method here that calls anything, the only state a proposal can be constructed in
is PROPOSED, and moving it anywhere else requires a `SpendDecision` naming a
person.

## The reservation is read from permissions.yaml, never decided here

`permissions.yaml` reserves `large_or_recurring_paid_api_spend` to the CEO.
`reserved_actions_for_spend` intersects what a proposal would trigger with what
that file actually reserves, the same way
`company/org_intelligence/recommendations.py` does - so the answer changes when
the CEO changes the reservation list, and not when this module is edited.

With no permissions supplied it fails *closed*: every candidate action is
returned. A caller who cannot read the file gets the stricter answer.

## What "large" means is configuration, and may be absent

Section 13 says do not invent a threshold. `SpendPolicy.approval_threshold`
defaults to `None`, and a `None` threshold does not mean "nothing is large" - it
means the size test is unavailable, so the recurrence test carries the whole
gate. A recurring paid external spend is CEO-reserved with or without a
threshold, because that is what the permissions file already says.

## A proposal is immutable; a decision is a separate record

Editing a proposal to say it was approved would put the approval and the request
in one file that only the last writer can be held to. `SpendDecision` is its own
record, references the proposal, names a human, and carries evidence.
`resolve()` reads the pair and reports the status - it never writes one.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Iterable, Mapping

from knowledge.company_os.records import Alternative, Evidence

from .common import (
    assert_day,
    assert_evidence_backed,
    assert_human,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    record_to_dict,
    text_tuple,
)
from .costs import PAID_EXTERNAL_CATEGORIES, CostCategory, Recurrence
from .errors import FinanceError, SpendAuthorityViolation
from .money import Money

# The permissions.yaml action a paid external spend triggers. The string is the
# one that file uses; `unreserved_action` below reports it if the file stops
# naming it, which is the rename detector org intelligence already established.
PAID_SPEND_RESERVED_ACTION = "large_or_recurring_paid_api_spend"


class SpendStatus(Enum):
    """Where a proposal stands. PROPOSED is the only one it can be born in."""

    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class SpendPolicy:
    """The company's spend thresholds, as configuration rather than belief.

    `approval_threshold=None` is the default and the honest state at bootstrap:
    no monthly figure has been set, so no size test runs. It does not weaken the
    recurrence gate, which comes from permissions.yaml and not from here.
    """

    approval_threshold: Money | None = None
    threshold_period: str = "monthly"
    recurring_paid_spend_requires_approval: bool = True
    source: str = ""

    def __post_init__(self) -> None:
        if self.approval_threshold is not None:
            if not isinstance(self.approval_threshold, Money):
                raise FinanceError("approval_threshold must be Money or None")
            if self.approval_threshold.is_negative:
                raise FinanceError("approval_threshold cannot be negative")
            if not self.source.strip():
                raise FinanceError(
                    "a spend threshold needs a source: which decision or document set it. "
                    "A number with no provenance is a policy this package invented "
                    "(brief section 13)"
                )
        if not isinstance(self.recurring_paid_spend_requires_approval, bool):
            raise FinanceError("recurring_paid_spend_requires_approval must be a boolean")
        if not isinstance(self.threshold_period, str) or not self.threshold_period.strip():
            raise FinanceError("threshold_period must name the period the threshold covers")

    @property
    def has_threshold(self) -> bool:
        return self.approval_threshold is not None

    def exceeds_threshold(self, amount: Money) -> bool | None:
        """True, False, or None when there is no threshold to test against."""
        if self.approval_threshold is None:
            return None
        if amount.currency != self.approval_threshold.currency:
            raise FinanceError(
                f"spend of {amount.currency} cannot be tested against a threshold in "
                f"{self.approval_threshold.currency}; nothing here converts a currency"
            )
        return amount > self.approval_threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_threshold": (
                self.approval_threshold.to_dict() if self.approval_threshold else None
            ),
            "threshold_period": self.threshold_period,
            "recurring_paid_spend_requires_approval": (
                self.recurring_paid_spend_requires_approval
            ),
            "source": self.source,
        }


def reserved_actions_for_spend(
    category: CostCategory,
    recurrence: Recurrence,
    amount: Money,
    *,
    policy: SpendPolicy | None = None,
    permissions: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """The permissions.yaml actions this spend would trigger, sorted.

    Two independent triggers, either of which is enough: the spend recurs, or it
    exceeds a threshold somebody configured. With no permissions mapping the
    function fails closed and returns every candidate it found.
    """
    rules = policy or SpendPolicy()
    candidates: set[str] = set()
    if category in PAID_EXTERNAL_CATEGORIES:
        if recurrence is Recurrence.RECURRING and rules.recurring_paid_spend_requires_approval:
            candidates.add(PAID_SPEND_RESERVED_ACTION)
        if rules.exceeds_threshold(amount):
            candidates.add(PAID_SPEND_RESERVED_ACTION)
    if permissions is None:
        return tuple(sorted(candidates))
    reserved = set(permissions.get("ceo_reserved", ()) or ())
    return tuple(sorted(candidates & reserved))


def unreserved_action(permissions: Mapping[str, Any]) -> tuple[str, ...]:
    """Empty unless permissions.yaml has stopped reserving paid spend.

    The rename detector for this package's single mapped action. If
    `ceo_reserved` drops `large_or_recurring_paid_api_spend`, nothing above
    fails - it quietly stops flagging - and `integrity.py` reports this instead.
    """
    reserved = set(permissions.get("ceo_reserved", ()) or ())
    return () if PAID_SPEND_RESERVED_ACTION in reserved else (PAID_SPEND_RESERVED_ACTION,)


@dataclass(frozen=True)
class SpendProposal:
    """A request to spend money, with everything a decider needs and no authority."""

    kind: ClassVar[str] = "spend_proposal"

    proposal_id: str
    service: str
    purpose: str
    category: CostCategory
    recurrence: Recurrence
    estimated_amount: Money
    period: str
    expected_benefit: str
    break_even_condition: str
    kill_condition: str
    evidence: tuple[Evidence, ...]
    proposed_by: str
    proposed_on: dt.date
    assumptions: tuple[str, ...] = ()
    alternatives: tuple[Alternative, ...] = ()
    requires_ceo_approval: bool = False
    reserved_actions: tuple[str, ...] = ()
    status: SpendStatus = SpendStatus.PROPOSED
    supersedes: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.proposal_id, "proposal_id")
        assert_ref(self.service, f"proposal {self.proposal_id!r} service")
        for name in ("purpose", "expected_benefit", "break_even_condition", "kill_condition"):
            assert_prose(getattr(self, name), f"proposal {self.proposal_id!r} {name}")
        assert_prose(self.proposed_by, f"proposal {self.proposal_id!r} proposed_by")
        if not isinstance(self.category, CostCategory):
            raise FinanceError(f"proposal {self.proposal_id!r}: category must be a CostCategory")
        if not isinstance(self.recurrence, Recurrence):
            raise FinanceError(f"proposal {self.proposal_id!r}: recurrence must be a Recurrence")
        if not isinstance(self.status, SpendStatus):
            raise FinanceError(f"proposal {self.proposal_id!r}: status must be a SpendStatus")
        if self.status is not SpendStatus.PROPOSED:
            raise SpendAuthorityViolation(
                f"proposal {self.proposal_id!r} cannot be created as "
                f"{self.status.value}. A proposal is born PROPOSED; anything else is a "
                "decision, and a decision is a separate record naming a person "
                "(brief section 12)"
            )
        if not isinstance(self.estimated_amount, Money):
            raise FinanceError(f"proposal {self.proposal_id!r}: estimated_amount must be Money")
        if self.estimated_amount.is_negative:
            raise FinanceError(
                f"proposal {self.proposal_id!r}: estimated_amount cannot be negative"
            )
        object.__setattr__(self, "proposed_on", assert_day(self.proposed_on, "proposed_on"))
        object.__setattr__(
            self, "assumptions", text_tuple(self.assumptions, "assumption")
        )
        object.__setattr__(self, "alternatives", _alternatives(self.alternatives))
        object.__setattr__(
            self,
            "reserved_actions",
            tuple(sorted({assert_ref(item, "reserved_action") for item in self.reserved_actions or ()})),
        )
        if not isinstance(self.requires_ceo_approval, bool):
            raise FinanceError(
                f"proposal {self.proposal_id!r}: requires_ceo_approval must be a boolean"
            )
        if self.recurrence is Recurrence.RECURRING and not self.period.strip():
            raise FinanceError(
                f"proposal {self.proposal_id!r}: a recurring spend must name its period"
            )
        if self.supersedes:
            assert_record_id(self.supersedes, f"proposal {self.proposal_id!r} supersedes")
        for name in ("period", "notes"):
            if not isinstance(getattr(self, name), str):
                raise FinanceError(f"proposal {self.proposal_id!r}: {name} must be a string")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"proposal {self.proposal_id!r} evidence",
            "a spend request has to point at what makes the estimate and the benefit "
            "checkable",
        )
        if self.reserved_actions and not self.requires_ceo_approval:
            raise SpendAuthorityViolation(
                f"proposal {self.proposal_id!r} names reserved actions "
                + ", ".join(self.reserved_actions)
                + " but does not require CEO approval"
            )
        if not self.alternatives:
            raise FinanceError(
                f"proposal {self.proposal_id!r}: name at least one alternative considered, "
                "even if it is doing nothing. A request with no alternative is a decision "
                "already taken"
            )

    # -- the four things a proposal is not ---------------------------------
    #
    # There is deliberately no pay(), subscribe(), execute(), approve() or
    # grant() on this class. `tests/test_company_finance.py` asserts their
    # absence by name, so adding one fails a test rather than shipping quietly.

    @property
    def currency(self) -> str:
        return self.estimated_amount.currency

    @property
    def is_recurring(self) -> bool:
        return self.recurrence is Recurrence.RECURRING

    def with_reservation(
        self,
        *,
        policy: SpendPolicy | None = None,
        permissions: Mapping[str, Any] | None = None,
    ) -> SpendProposal:
        """The same proposal with the reservation flags computed from permissions.

        A new value, not a mutation, and it only ever *adds* a gate: a proposal
        that already requires CEO approval keeps requiring it even if the policy
        would not have triggered.
        """
        from dataclasses import replace

        actions = reserved_actions_for_spend(
            self.category,
            self.recurrence,
            self.estimated_amount,
            policy=policy,
            permissions=permissions,
        )
        merged = tuple(sorted(set(actions) | set(self.reserved_actions)))
        return replace(
            self,
            reserved_actions=merged,
            requires_ceo_approval=self.requires_ceo_approval or bool(merged),
        )

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpendProposal:
        return cls(
            proposal_id=data["proposal_id"],
            service=data["service"],
            purpose=data["purpose"],
            category=CostCategory(data["category"]),
            recurrence=Recurrence(data["recurrence"]),
            estimated_amount=Money.from_dict(data["estimated_amount"], "estimated_amount"),
            period=data.get("period", ""),
            expected_benefit=data["expected_benefit"],
            break_even_condition=data["break_even_condition"],
            kill_condition=data["kill_condition"],
            evidence=evidence_tuple(data.get("evidence")),
            proposed_by=data["proposed_by"],
            proposed_on=assert_day(data["proposed_on"], "proposed_on"),
            assumptions=tuple(data.get("assumptions", ())),
            alternatives=_alternatives(data.get("alternatives", ())),
            requires_ceo_approval=bool(data.get("requires_ceo_approval", False)),
            reserved_actions=tuple(data.get("reserved_actions", ())),
            status=SpendStatus(data.get("status", "proposed")),
            supersedes=data.get("supersedes", ""),
            notes=data.get("notes", ""),
        )


def _alternatives(value: Any) -> tuple[Alternative, ...]:
    if not value:
        return ()
    if isinstance(value, (str, bytes, Alternative)):
        raise FinanceError("alternatives must be a sequence of Alternative records")
    out: list[Alternative] = []
    for item in value:
        if isinstance(item, Alternative):
            out.append(item)
        elif isinstance(item, dict):
            try:
                out.append(Alternative.from_dict(item))
            except (KeyError, ValueError) as exc:
                raise FinanceError(f"malformed alternative: {exc}") from exc
        else:
            raise FinanceError(
                f"alternatives must be Alternative records, got {type(item).__name__}"
            )
    return tuple(out)


@dataclass(frozen=True)
class SpendDecision:
    """A human's answer to a proposal. The only thing that moves it off PROPOSED."""

    kind: ClassVar[str] = "spend_decision"

    decision_id: str
    proposal_id: str
    status: SpendStatus
    decided_by: str
    decided_on: dt.date
    reason: str
    evidence: tuple[Evidence, ...] = ()
    is_ceo: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.decision_id, "decision_id")
        assert_record_id(self.proposal_id, "proposal_id")
        if not isinstance(self.status, SpendStatus):
            raise FinanceError(f"decision {self.decision_id!r}: status must be a SpendStatus")
        if self.status is SpendStatus.PROPOSED:
            raise FinanceError(
                f"decision {self.decision_id!r}: PROPOSED is where a proposal starts, not "
                "something anybody decides"
            )
        assert_human(self.decided_by, f"decision {self.decision_id!r} decided_by")
        object.__setattr__(self, "decided_on", assert_day(self.decided_on, "decided_on"))
        assert_prose(self.reason, f"decision {self.decision_id!r} reason")
        if not isinstance(self.is_ceo, bool):
            raise FinanceError(f"decision {self.decision_id!r}: is_ceo must be a boolean")
        if not isinstance(self.notes, str):
            raise FinanceError(f"decision {self.decision_id!r}: notes must be a string")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if self.status is SpendStatus.APPROVED:
            assert_evidence_backed(
                self.evidence,
                f"decision {self.decision_id!r} evidence",
                "an approval has to point at where it was given - a message, a minute, a "
                "commit - or it is an approval nobody can produce",
            )

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpendDecision:
        return cls(
            decision_id=data["decision_id"],
            proposal_id=data["proposal_id"],
            status=SpendStatus(data["status"]),
            decided_by=data["decided_by"],
            decided_on=assert_day(data["decided_on"], "decided_on"),
            reason=data["reason"],
            evidence=evidence_tuple(data.get("evidence")),
            is_ceo=bool(data.get("is_ceo", False)),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class ResolvedProposal:
    """A proposal read together with its decisions. Reading changes nothing."""

    proposal: SpendProposal
    decisions: tuple[SpendDecision, ...]
    status: SpendStatus
    blocked_reasons: tuple[str, ...]

    @property
    def is_approved(self) -> bool:
        """True only when an approval exists *and* nothing blocks it."""
        return self.status is SpendStatus.APPROVED and not self.blocked_reasons

    @property
    def latest_decision(self) -> SpendDecision | None:
        return self.decisions[-1] if self.decisions else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal.proposal_id,
            "status": self.status.value,
            "decisions": [decision.decision_id for decision in self.decisions],
            "blocked_reasons": list(self.blocked_reasons),
            "is_approved": self.is_approved,
        }


def resolve(
    proposal: SpendProposal, decisions: Iterable[SpendDecision] = ()
) -> ResolvedProposal:
    """Where a proposal stands, given the decisions recorded against it.

    A CEO-reserved proposal approved by somebody who is not the CEO is reported
    as blocked, not as approved. That is section 27 in one branch: finance
    records the approval it was given and says when it is not the one required.
    """
    own = sorted(
        (
            decision
            for decision in decisions
            if decision.proposal_id == proposal.proposal_id
        ),
        key=lambda decision: (decision.decided_on, decision.decision_id),
    )
    blocked: list[str] = []
    status = proposal.status
    if own:
        status = own[-1].status
    approvals = [item for item in own if item.status is SpendStatus.APPROVED]
    if approvals and proposal.requires_ceo_approval:
        if not any(item.is_ceo for item in approvals):
            blocked.append(
                f"proposal {proposal.proposal_id!r} is CEO-reserved ("
                + ", ".join(proposal.reserved_actions or (PAID_SPEND_RESERVED_ACTION,))
                + ") and no decision on it is marked as the CEO's"
            )
    if proposal.requires_ceo_approval and not approvals and status is SpendStatus.APPROVED:
        blocked.append(
            f"proposal {proposal.proposal_id!r} reads as approved with no approval decision"
        )
    return ResolvedProposal(
        proposal=proposal,
        decisions=tuple(own),
        status=status,
        blocked_reasons=tuple(blocked),
    )

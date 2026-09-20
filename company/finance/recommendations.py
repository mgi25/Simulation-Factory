"""What the numbers suggest doing - as a record somebody reads, never an action.

## Advisory, in the same shape organizational intelligence already uses

A `FinancialRecommendation` names a type, a subject, the evidence behind it and
what it would cost to be wrong. It has no method that changes anything, and the
only CEO-reserved type is the one that asks to spend money, where the
reservation is read from `permissions.yaml` rather than decided here.

## Handoff rather than a second vocabulary

`company/org_intelligence` already defines `REVISE_BUDGET` and
`GATHER_MORE_EVIDENCE` as organizational recommendation types with their own
approval semantics, review states and change-proposal machinery. Section 24 asks
for reference and handoff instead of conflicting company-change semantics, so
`ORG_INTELLIGENCE_EQUIVALENT` maps the overlapping finance types onto the
organizational type id they belong to, and `handoff_to` carries it on the record.

The mapping is a table of strings, not an import: `company/finance` depends on
no other Company OS subsystem, which is what keeps the capsule edge from
organizational intelligence to finance acyclic. A caller that holds both
packages resolves the string; one that holds only finance still reads a
recommendation that says where the decision belongs.

## Why there is no priority number

Ranking recommendations by a computed score is the multi-objective collapse
section 23 forbids, one level down. What a reader gets instead is the evidence,
the subject and the type, and a human decides what matters this week.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Mapping

from knowledge.company_os.records import Evidence

from .common import (
    SubjectRef,
    assert_day,
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    record_to_dict,
    text_tuple,
)
from .errors import FinanceError, SpendAuthorityViolation
from .proposals import PAID_SPEND_RESERVED_ACTION


class FinancialRecommendationType(Enum):
    """Section 24's list, one value each. None of them does anything."""

    INVESTIGATE_COST = "investigate_cost"
    REDUCE_COST = "reduce_cost"
    REVISE_BUDGET = "revise_budget"
    APPROVE_SPEND = "approve_spend"
    REJECT_SPEND = "reject_spend"
    GATHER_MORE_EVIDENCE = "gather_more_evidence"
    CONTINUE_INVESTMENT = "continue_investment"
    STOP_INVESTMENT = "stop_investment"
    REVIEW_SUBSCRIPTION = "review_subscription"


# Finance types that organizational intelligence already has a type for. The
# value is that package's `RecommendationType` id, carried as a string so this
# package imports nothing from it.
ORG_INTELLIGENCE_EQUIVALENT: dict[FinancialRecommendationType, str] = {
    FinancialRecommendationType.REVISE_BUDGET: "revise_budget",
    FinancialRecommendationType.GATHER_MORE_EVIDENCE: "gather_more_evidence",
    FinancialRecommendationType.INVESTIGATE_COST: "investigate",
}

# The one type that asks for money to be committed. Its reservation still comes
# from permissions.yaml; this set only says which type to test.
_SPEND_TYPES = frozenset({FinancialRecommendationType.APPROVE_SPEND})


@dataclass(frozen=True)
class FinancialRecommendation:
    """A proposed financial action. Reading it changes nothing."""

    kind: ClassVar[str] = "financial_recommendation"

    recommendation_id: str
    type: FinancialRecommendationType
    subject: SubjectRef
    rationale: str
    evidence: tuple[Evidence, ...]
    recommended_by: str
    recommended_on: dt.date
    expected_effect: str = ""
    missing_measurements: tuple[str, ...] = ()
    record_refs: tuple[str, ...] = ()
    spend_proposal_id: str = ""
    requires_ceo_approval: bool = False
    reserved_actions: tuple[str, ...] = ()
    handoff_to: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.recommendation_id, "recommendation_id")
        if not isinstance(self.type, FinancialRecommendationType):
            raise FinanceError(
                f"recommendation {self.recommendation_id!r}: type must be a "
                "FinancialRecommendationType"
            )
        if not isinstance(self.subject, SubjectRef):
            raise FinanceError(
                f"recommendation {self.recommendation_id!r}: subject must be a SubjectRef"
            )
        assert_prose(self.rationale, f"recommendation {self.recommendation_id!r} rationale")
        assert_prose(
            self.recommended_by, f"recommendation {self.recommendation_id!r} recommended_by"
        )
        object.__setattr__(
            self, "recommended_on", assert_day(self.recommended_on, "recommended_on")
        )
        object.__setattr__(
            self,
            "missing_measurements",
            text_tuple(self.missing_measurements, "missing measurement"),
        )
        object.__setattr__(
            self,
            "record_refs",
            tuple(assert_ref(item, "record_ref") for item in self.record_refs or ()),
        )
        object.__setattr__(
            self,
            "reserved_actions",
            tuple(
                sorted({assert_ref(item, "reserved_action") for item in self.reserved_actions or ()})
            ),
        )
        if self.spend_proposal_id:
            assert_record_id(
                self.spend_proposal_id,
                f"recommendation {self.recommendation_id!r} spend_proposal_id",
            )
        if not isinstance(self.requires_ceo_approval, bool):
            raise FinanceError(
                f"recommendation {self.recommendation_id!r}: requires_ceo_approval must be "
                "a boolean"
            )
        for name in ("expected_effect", "handoff_to", "notes"):
            if not isinstance(getattr(self, name), str):
                raise FinanceError(
                    f"recommendation {self.recommendation_id!r}: {name} must be a string"
                )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_evidence_backed(
            self.evidence,
            f"recommendation {self.recommendation_id!r} evidence",
            "a financial recommendation with no evidence is an opinion with a record id",
        )
        if self.reserved_actions and not self.requires_ceo_approval:
            raise SpendAuthorityViolation(
                f"recommendation {self.recommendation_id!r} names reserved actions "
                + ", ".join(self.reserved_actions)
                + " but does not require CEO approval"
            )
        if self.type in _SPEND_TYPES and not self.spend_proposal_id:
            raise FinanceError(
                f"recommendation {self.recommendation_id!r}: a recommendation to approve "
                "spend must reference the SpendProposal it is about. Finance does not "
                "approve an amount, it points at the request somebody made"
            )
        expected = ORG_INTELLIGENCE_EQUIVALENT.get(self.type)
        if expected and self.handoff_to != expected:
            raise FinanceError(
                f"recommendation {self.recommendation_id!r}: {self.type.value} overlaps "
                f"organizational intelligence's {expected!r}. Set handoff_to={expected!r} "
                "so the decision stays in one place rather than forking into two "
                "vocabularies (brief section 24)"
            )
        if not expected and self.handoff_to:
            raise FinanceError(
                f"recommendation {self.recommendation_id!r}: {self.type.value} has no "
                "organizational-intelligence equivalent, so handoff_to must be empty"
            )

    # There is deliberately no apply(), execute(), pay() or approve() here.
    # `tests/test_company_finance.py` asserts their absence by name.

    @property
    def hands_off_to_org_intelligence(self) -> bool:
        return bool(self.handoff_to)

    def with_reservation(
        self, *, permissions: Mapping[str, Any] | None = None
    ) -> FinancialRecommendation:
        """Flag the spend type as CEO-reserved when permissions.yaml says so.

        Fails closed: with no permissions mapping, a spend recommendation is
        reserved. Never removes a reservation a caller already set.
        """
        from dataclasses import replace

        if self.type not in _SPEND_TYPES:
            return self
        if permissions is None:
            actions = (PAID_SPEND_RESERVED_ACTION,)
        else:
            reserved = set(permissions.get("ceo_reserved", ()) or ())
            actions = (
                (PAID_SPEND_RESERVED_ACTION,)
                if PAID_SPEND_RESERVED_ACTION in reserved
                else ()
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
    def from_dict(cls, data: dict[str, Any]) -> FinancialRecommendation:
        return cls(
            recommendation_id=data["recommendation_id"],
            type=FinancialRecommendationType(data["type"]),
            subject=SubjectRef.from_dict(data["subject"]),
            rationale=data["rationale"],
            evidence=evidence_tuple(data.get("evidence")),
            recommended_by=data["recommended_by"],
            recommended_on=assert_day(data["recommended_on"], "recommended_on"),
            expected_effect=data.get("expected_effect", ""),
            missing_measurements=tuple(data.get("missing_measurements", ())),
            record_refs=tuple(data.get("record_refs", ())),
            spend_proposal_id=data.get("spend_proposal_id", ""),
            requires_ceo_approval=bool(data.get("requires_ceo_approval", False)),
            reserved_actions=tuple(data.get("reserved_actions", ())),
            handoff_to=data.get("handoff_to", ""),
            notes=data.get("notes", ""),
        )

"""A finding: what the signals together support, and what would overturn it.

## Why this layer exists at all

A signal says `role_overlap`. A finding says *these two roles are redundant, on
this evidence, over this window, and here is what would change my mind*. The gap
between those two sentences is the whole reason the brief asks for two record
types instead of one: a company that treats every measurement as a conclusion
reorganizes itself around noise.

So a finding cannot be built from nothing, and it carries four things a signal
does not:

- `counterevidence` - the observations that point the other way, kept beside the
  ones that agree rather than discarded when the conclusion was chosen;
- `limitations` - always non-empty, because a finding computed over a window is
  limited to that window whether or not its author thought to say so, and this
  class adds that sentence itself;
- `what_would_change_it` - required. A claim nobody can imagine being wrong is
  not a finding, it is a position;
- `strength` - derived, in one place, from what the signals actually measured.

## Evidence strength is computed, not asserted

`evidence_strength` is eight lines and reads its inputs off the signals: how
many of them measured a number at all, how many crossed their threshold, whether
any sample was too small, and whether counterevidence exists. It is coarse on
purpose - three levels - because a finer scale would invite the reader to
believe a precision that three organizational signals cannot carry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import (
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    nonempty_text_tuple,
    optional_ref,
    text_tuple,
)
from .errors import OrgIntelligenceError
from .signals import OrganizationalSignal
from .window import ReviewWindow


class FindingCategory(Enum):
    """Section 3 of the brief, one value each."""

    CAPABILITY_RISK = "capability_risk"
    REDUNDANCY = "redundancy"
    WORKFORCE_GAP = "workforce_gap"
    WORKFLOW_INEFFICIENCY = "workflow_inefficiency"
    RESOURCE_INEFFICIENCY = "resource_inefficiency"
    MANAGEMENT_BOTTLENECK = "management_bottleneck"
    APPROVAL_BOTTLENECK = "approval_bottleneck"
    KNOWLEDGE_BLOAT = "knowledge_bloat"
    ORGANIZATIONAL_DEBT = "organizational_debt"
    AUTOMATION_CANDIDATE = "automation_candidate"
    STRUCTURAL_FACT = "structural_fact"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceStrength(Enum):
    """How much the evidence carries. Three levels, deliberately coarse."""

    INSUFFICIENT = "insufficient"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


COUNTEREVIDENCE_LIMITATION = (
    "counterevidence was recorded against this finding; read it before acting"
)


def evidence_strength(
    signals: Iterable[OrganizationalSignal],
    *,
    counterevidence: Iterable[Evidence] = (),
) -> EvidenceStrength:
    """Derive strength from what the signals measured. One rule, in one place.

    Deliberately blunt: strength rises with the number of signals that both
    measured a value and crossed their own declared threshold, and it is capped
    by the two things that should cap it - a sample nobody should read as a rate,
    and evidence pointing the other way.
    """
    items = tuple(signals)
    if not items:
        return EvidenceStrength.INSUFFICIENT
    breaching = [item for item in items if item.breaches_threshold is True]
    measured = [item for item in items if item.measured]
    small = any(item.measurement.small_sample for item in items)

    if not measured:
        return EvidenceStrength.INSUFFICIENT
    if len(breaching) >= 2 and len(items) >= 2:
        level = EvidenceStrength.STRONG
    elif breaching:
        level = EvidenceStrength.MODERATE
    else:
        level = EvidenceStrength.WEAK

    if small and level is EvidenceStrength.STRONG:
        level = EvidenceStrength.MODERATE
    if tuple(counterevidence) and level is EvidenceStrength.STRONG:
        level = EvidenceStrength.MODERATE
    return level


@dataclass(frozen=True)
class OrganizationalFinding:
    """A claim about the organization, with everything needed to argue with it."""

    finding_id: str
    category: FindingCategory
    subjects: tuple[str, ...]
    statement: str
    window: ReviewWindow
    signal_ids: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()
    strength: EvidenceStrength = EvidenceStrength.WEAK
    limitations: tuple[str, ...] = ()
    counterevidence: tuple[Evidence, ...] = ()
    what_would_change_it: tuple[str, ...] = ()
    review_id: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.finding_id, "finding_id")
        if not isinstance(self.category, FindingCategory):
            raise OrgIntelligenceError("finding category must be a FindingCategory")
        if not isinstance(self.strength, EvidenceStrength):
            raise OrgIntelligenceError("finding strength must be an EvidenceStrength")
        if not isinstance(self.window, ReviewWindow):
            raise OrgIntelligenceError("finding window must be a ReviewWindow")
        assert_prose(self.statement, f"finding {self.finding_id} statement")
        object.__setattr__(
            self,
            "subjects",
            tuple(assert_ref(item, "finding subject") for item in self.subjects or ()),
        )
        object.__setattr__(
            self,
            "signal_ids",
            tuple(assert_record_id(item, "finding signal_id") for item in self.signal_ids or ()),
        )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        object.__setattr__(self, "counterevidence", evidence_tuple(self.counterevidence))
        object.__setattr__(
            self, "review_id", optional_ref(self.review_id, "finding review_id")
        )
        if not isinstance(self.notes, str):
            raise OrgIntelligenceError("finding notes must be a string")

        if not self.subjects:
            raise OrgIntelligenceError(
                f"finding {self.finding_id}: name what it is about; a finding with no "
                "subject cannot be acted on or argued with"
            )
        if len(set(self.signal_ids)) != len(self.signal_ids):
            raise OrgIntelligenceError(
                f"finding {self.finding_id}: duplicate signal ids in supporting evidence"
            )
        if not self.signal_ids:
            raise OrgIntelligenceError(
                f"finding {self.finding_id}: a finding combines one or more signals. "
                "A conclusion with no observation underneath it is an opinion"
            )
        assert_evidence_backed(
            self.evidence,
            f"finding {self.finding_id} evidence",
            "section 3 of the brief: no finding with zero evidence. Even an "
            "insufficient_evidence finding points at what was examined",
        )
        object.__setattr__(
            self,
            "what_would_change_it",
            nonempty_text_tuple(
                self.what_would_change_it,
                f"finding {self.finding_id} what_would_change_it",
                "a claim nobody can imagine being wrong is a position, not a finding",
            ),
        )

        # The window limitation is true of every finding whether or not its
        # author wrote it down, so the record writes it.
        limitations = text_tuple(self.limitations, "finding limitations")
        if self.window.limitation not in limitations:
            limitations = limitations + (self.window.limitation,)
        if self.counterevidence and COUNTEREVIDENCE_LIMITATION not in limitations:
            limitations = limitations + (COUNTEREVIDENCE_LIMITATION,)
        object.__setattr__(self, "limitations", limitations)

    @property
    def has_counterevidence(self) -> bool:
        return bool(self.counterevidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "category": self.category.value,
            "subjects": list(self.subjects),
            "statement": self.statement,
            "window": self.window.to_dict(),
            "signal_ids": list(self.signal_ids),
            "evidence": [to_jsonable(item) for item in self.evidence],
            "strength": self.strength.value,
            "limitations": list(self.limitations),
            "counterevidence": [to_jsonable(item) for item in self.counterevidence],
            "what_would_change_it": list(self.what_would_change_it),
            "review_id": self.review_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationalFinding:
        return cls(
            finding_id=data["finding_id"],
            category=FindingCategory(data["category"]),
            subjects=tuple(data.get("subjects", ())),
            statement=data["statement"],
            window=ReviewWindow.from_dict(data["window"]),
            signal_ids=tuple(data.get("signal_ids", ())),
            evidence=evidence_tuple(data.get("evidence")),
            strength=EvidenceStrength(data.get("strength", EvidenceStrength.WEAK.value)),
            limitations=tuple(data.get("limitations", ())),
            counterevidence=evidence_tuple(data.get("counterevidence")),
            what_would_change_it=tuple(data.get("what_would_change_it", ())),
            review_id=data.get("review_id", ""),
            notes=data.get("notes", ""),
        )


def build_finding(
    finding_id: str,
    category: FindingCategory,
    *,
    statement: str,
    signals: Iterable[OrganizationalSignal],
    subjects: Iterable[str] = (),
    window: ReviewWindow | None = None,
    evidence: Iterable[Evidence] = (),
    counterevidence: Iterable[Evidence] = (),
    what_would_change_it: Iterable[str] = (),
    limitations: Iterable[str] = (),
    review_id: str = "",
    notes: str = "",
) -> OrganizationalFinding:
    """Assemble a finding from its signals, deriving what can be derived.

    Subjects, window, evidence and strength all come from the signals unless the
    caller overrides them, so a finding cannot quietly claim a window its
    evidence does not cover or a subject none of its signals looked at. Every
    signal caveat becomes a limitation, which is how a small sample survives the
    trip from measurement to claim.
    """
    items = tuple(signals)
    if not items:
        raise OrgIntelligenceError(
            f"finding {finding_id}: build_finding needs at least one signal"
        )
    chosen_window = window or _covering_window(items)
    chosen_subjects = tuple(subjects) or tuple(dict.fromkeys(item.subject for item in items))
    collected = tuple(evidence) or tuple(
        dict.fromkeys(item for signal in items for item in signal.evidence)
    )
    caveats = tuple(dict.fromkeys(caveat for signal in items for caveat in signal.caveats))
    absences = tuple(
        f"{signal.signal_id}: {missing}"
        for signal in items
        for missing in signal.missing_measurements
    )
    return OrganizationalFinding(
        finding_id=finding_id,
        category=category,
        subjects=chosen_subjects,
        statement=statement,
        window=chosen_window,
        signal_ids=tuple(item.signal_id for item in items),
        evidence=collected,
        strength=evidence_strength(items, counterevidence=counterevidence),
        limitations=tuple(dict.fromkeys(tuple(limitations) + caveats + absences)),
        counterevidence=tuple(counterevidence),
        what_would_change_it=tuple(what_would_change_it),
        review_id=review_id,
        notes=notes,
    )


def _covering_window(signals: tuple[OrganizationalSignal, ...]) -> ReviewWindow:
    """The smallest window containing every signal's window.

    Widening rather than picking one: a finding built from a 7-day signal and a
    30-day signal describes 30 days, and saying otherwise would be the
    unrelated-periods mistake section 1 warns about.
    """
    return ReviewWindow(
        start=min(signal.window.start for signal in signals),
        end=max(signal.window.end for signal in signals),
    )

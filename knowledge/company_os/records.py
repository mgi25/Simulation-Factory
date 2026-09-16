"""Five record types, and the structural reason a fact is not a hypothesis.

Constitution rule 16 - *facts != hypotheses != decisions* - is the one rule a
knowledge store cannot honour by convention. Convention degrades: a confident
guess gets written down, read back six weeks later by a session with no memory
of who wrote it, and spent as though it were measured. The distinction has to
be in the shape of the record, so that a guess *cannot be stored in the shape
of a fact*.

So these are five sibling types with no inheritance between them, and they
differ where it matters:

    Fact                 Requires evidence. Construction with an empty evidence
                         tuple raises, with an error that names what the caller
                         actually has: a hypothesis. Carries a freshness class.
    Hypothesis           Requires a `predicted_observation` and a `test_plan` -
                         the two fields that make it falsifiable - and evidence
                         is optional. Carries no freshness class, because
                         freshness answers "is this still true?" and an open
                         hypothesis was never asserted to be true. It carries a
                         status instead: open, supported, falsified, abandoned.
    Decision             Requires `why`, alternatives with reasons, risks,
                         `reconsider_if`, and a `rollback` plan (rule 10).
    ExperimentLearning   Requires the changed variables and the locked ones
                         (rule 9). An experiment that cannot say what it held
                         constant did not isolate anything.
    FailureLearning      Requires a root cause, how it was detected, and a
                         prevention (rule 14).

Crossing from hypothesis to fact happens in exactly one place, `promote()`, and
it demands what the promotion is actually made of: a supported status and
evidence. The resulting `Fact` records `derived_from`, so the chain from guess
to claim survives in the store.

## Evidence is a pointer

`Evidence.ref` is held to the same reference discipline as a context manifest:
a test node id, a commit sha, a validation artefact path, a URL. Pasting a
measurement's output into the record would make the store as expensive to read
as the thing it exists to replace.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, ClassVar

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, as_opt_date, as_tuple
from knowledge.company_os.freshness import Freshness, default_recheck_on

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


class KnowledgeError(ValueError):
    """A record that would corrupt the store if it were written."""


class RecordStatus(Enum):
    """Lifecycle of a claim that is currently believed."""

    ACTIVE = "active"
    NEEDS_REVALIDATION = "needs_revalidation"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class HypothesisStatus(Enum):
    """Lifecycle of a claim that is under test."""

    OPEN = "open"
    SUPPORTED = "supported"
    FALSIFIED = "falsified"
    ABANDONED = "abandoned"


class DecisionStatus(Enum):
    ACTIVE = "active"
    UNDER_RECONSIDERATION = "under_reconsideration"
    SUPERSEDED = "superseded"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class Evidence:
    """A pointer to something checkable, plus what it is."""

    kind: str  # test | measurement | render | commit | document | external | observation
    ref: str
    note: str = ""

    def __post_init__(self) -> None:
        assert_text(self.kind, "evidence kind")
        assert_reference(self.ref, "evidence ref")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        return cls(kind=data["kind"], ref=data["ref"], note=data.get("note", ""))


@dataclass(frozen=True)
class Alternative:
    """An option that was not taken, and why it was not."""

    option: str
    why_not: str

    def __post_init__(self) -> None:
        assert_text(self.option, "alternative option")
        assert_text(self.why_not, "alternative why_not")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Alternative:
        return cls(option=data["option"], why_not=data["why_not"])


def _assert_id(value: str, kind: str) -> None:
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        raise KnowledgeError(
            f"{kind} id {value!r} must be lowercase [a-z0-9._-], start alphanumeric, "
            "and be at most 80 characters - record ids are also filenames"
        )


def _assert_confidence(value: float, kind: str) -> None:
    if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise KnowledgeError(f"{kind} confidence must be between 0.0 and 1.0, got {value!r}")


def _evidence(data: Any) -> tuple[Evidence, ...]:
    if not data:
        return ()
    return tuple(e if isinstance(e, Evidence) else Evidence.from_dict(e) for e in data)


@dataclass(frozen=True)
class Fact:
    """Something we have checked, with the evidence that lets anyone recheck it."""

    kind: ClassVar[str] = "fact"

    id: str
    statement: str
    evidence: tuple[Evidence, ...]
    source: str
    created: dt.date
    freshness: Freshness
    confidence: float = 1.0
    recheck_on: dt.date | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    contradicts: tuple[str, ...] = ()
    related_tasks: tuple[str, ...] = ()
    related_experiments: tuple[str, ...] = ()
    related_commits: tuple[str, ...] = ()
    derived_from: str = ""  # hypothesis id, when this fact was promoted
    revalidation_reason: str = ""

    def __post_init__(self) -> None:
        _assert_id(self.id, "fact")
        assert_text(self.statement, "fact statement")
        assert_text(self.source, "fact source")
        _assert_confidence(self.confidence, "fact")
        if not self.evidence:
            raise KnowledgeError(
                f"fact {self.id!r} has no evidence. A claim without evidence is a "
                "Hypothesis - record it as one, test it, then promote() it."
            )
        if self.recheck_on is None:
            object.__setattr__(self, "recheck_on", default_recheck_on(self.freshness, self.created))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fact:
        return cls(
            id=data["id"],
            statement=data["statement"],
            evidence=_evidence(data.get("evidence")),
            source=data["source"],
            created=as_date(data["created"], "created"),
            freshness=Freshness(data["freshness"]),
            confidence=float(data.get("confidence", 1.0)),
            recheck_on=as_opt_date(data.get("recheck_on"), "recheck_on"),
            status=RecordStatus(data.get("status", "active")),
            contradicts=as_tuple(data.get("contradicts")),
            related_tasks=as_tuple(data.get("related_tasks")),
            related_experiments=as_tuple(data.get("related_experiments")),
            related_commits=as_tuple(data.get("related_commits")),
            derived_from=data.get("derived_from", ""),
            revalidation_reason=data.get("revalidation_reason", ""),
        )


@dataclass(frozen=True)
class Hypothesis:
    """Something we believe might be true, written so it can be proved wrong.

    No `freshness` field, and that absence is the design. Freshness answers "is
    this still true?"; an open hypothesis never claimed to be true, so the
    question does not apply. Its lifecycle is `status`, and the only route to
    fact-hood is `promote()`.
    """

    kind: ClassVar[str] = "hypothesis"

    id: str
    statement: str
    rationale: str
    predicted_observation: str
    test_plan: str
    source: str
    created: dt.date
    status: HypothesisStatus = HypothesisStatus.OPEN
    confidence: float = 0.5
    evidence: tuple[Evidence, ...] = ()
    contradicts: tuple[str, ...] = ()
    related_tasks: tuple[str, ...] = ()
    related_experiments: tuple[str, ...] = ()
    related_commits: tuple[str, ...] = ()
    outcome_note: str = ""

    def __post_init__(self) -> None:
        _assert_id(self.id, "hypothesis")
        assert_text(self.statement, "hypothesis statement")
        assert_text(self.rationale, "hypothesis rationale")
        assert_text(
            self.predicted_observation,
            "hypothesis predicted_observation (what would be seen if it holds)",
        )
        assert_text(self.test_plan, "hypothesis test_plan (how it would be falsified)")
        assert_text(self.source, "hypothesis source")
        _assert_confidence(self.confidence, "hypothesis")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hypothesis:
        return cls(
            id=data["id"],
            statement=data["statement"],
            rationale=data["rationale"],
            predicted_observation=data["predicted_observation"],
            test_plan=data["test_plan"],
            source=data["source"],
            created=as_date(data["created"], "created"),
            status=HypothesisStatus(data.get("status", "open")),
            confidence=float(data.get("confidence", 0.5)),
            evidence=_evidence(data.get("evidence")),
            contradicts=as_tuple(data.get("contradicts")),
            related_tasks=as_tuple(data.get("related_tasks")),
            related_experiments=as_tuple(data.get("related_experiments")),
            related_commits=as_tuple(data.get("related_commits")),
            outcome_note=data.get("outcome_note", ""),
        )


@dataclass(frozen=True)
class Decision:
    """A choice, with everything needed to revisit or undo it.

    `reconsider_if` and `rollback` are required because a decision without them
    is a decision nobody can safely revisit - constitution rules 10 and 20. The
    reconsideration and rollback transitions in `ledger.DecisionLedger` change
    only `status` and add a reason; every field recorded at decision time
    survives unchanged, because the point of the ledger is to show what was
    believed *then*.
    """

    kind: ClassVar[str] = "decision"

    id: str
    decision: str
    why: str
    evidence: tuple[Evidence, ...]
    alternatives: tuple[Alternative, ...]
    risks: tuple[str, ...]
    reconsider_if: tuple[str, ...]
    rollback: str
    source: str
    created: dt.date
    status: DecisionStatus = DecisionStatus.ACTIVE
    related_experiments: tuple[str, ...] = ()
    related_tasks: tuple[str, ...] = ()
    related_commits: tuple[str, ...] = ()
    superseded_by: str = ""
    reconsideration_reason: str = ""
    rollback_reason: str = ""

    def __post_init__(self) -> None:
        _assert_id(self.id, "decision")
        assert_text(self.decision, "decision")
        assert_text(self.why, "decision why")
        assert_text(self.source, "decision source")
        assert_text(self.rollback, "decision rollback (constitution rule 10: rollback always)")
        if not self.evidence:
            raise KnowledgeError(f"decision {self.id!r}: evidence is required (rule 7)")
        if not self.alternatives:
            raise KnowledgeError(
                f"decision {self.id!r}: record at least one alternative and why it was "
                "not taken - a decision with no alternatives was not a decision"
            )
        if not self.reconsider_if:
            raise KnowledgeError(
                f"decision {self.id!r}: record at least one condition that would cause "
                "this to be reconsidered, or it can never be revisited deliberately"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Decision:
        return cls(
            id=data["id"],
            decision=data["decision"],
            why=data["why"],
            evidence=_evidence(data.get("evidence")),
            alternatives=tuple(
                a if isinstance(a, Alternative) else Alternative.from_dict(a)
                for a in data.get("alternatives", ())
            ),
            risks=as_tuple(data.get("risks")),
            reconsider_if=as_tuple(data.get("reconsider_if")),
            rollback=data["rollback"],
            source=data["source"],
            created=as_date(data["created"], "created"),
            status=DecisionStatus(data.get("status", "active")),
            related_experiments=as_tuple(data.get("related_experiments")),
            related_tasks=as_tuple(data.get("related_tasks")),
            related_commits=as_tuple(data.get("related_commits")),
            superseded_by=data.get("superseded_by", ""),
            reconsideration_reason=data.get("reconsideration_reason", ""),
            rollback_reason=data.get("rollback_reason", ""),
        )


@dataclass(frozen=True)
class ExperimentLearning:
    """What one experiment taught, and the variables that make it mean anything."""

    kind: ClassVar[str] = "experiment_learning"

    id: str
    experiment_id: str
    question: str
    variables_changed: tuple[str, ...]
    variables_locked: tuple[str, ...]
    observation: str
    learning: str
    evidence: tuple[Evidence, ...]
    source: str
    created: dt.date
    freshness: Freshness
    confidence: float = 0.8
    recheck_on: dt.date | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    generalises: str = ""  # the scope this is believed to hold over
    contradicts: tuple[str, ...] = ()
    related_tasks: tuple[str, ...] = ()
    related_commits: tuple[str, ...] = ()
    revalidation_reason: str = ""

    def __post_init__(self) -> None:
        _assert_id(self.id, "experiment_learning")
        assert_reference(self.experiment_id, "experiment_id")
        assert_text(self.question, "experiment question")
        assert_text(self.observation, "experiment observation")
        assert_text(self.learning, "experiment learning")
        assert_text(self.source, "experiment source")
        _assert_confidence(self.confidence, "experiment_learning")
        if not self.variables_changed:
            raise KnowledgeError(
                f"experiment_learning {self.id!r}: name the changed variable(s). "
                "An experiment that cannot say what it varied isolated nothing (rule 9)."
            )
        if not self.evidence:
            raise KnowledgeError(f"experiment_learning {self.id!r}: evidence is required")
        if self.recheck_on is None:
            object.__setattr__(self, "recheck_on", default_recheck_on(self.freshness, self.created))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentLearning:
        return cls(
            id=data["id"],
            experiment_id=data["experiment_id"],
            question=data["question"],
            variables_changed=as_tuple(data.get("variables_changed")),
            variables_locked=as_tuple(data.get("variables_locked")),
            observation=data["observation"],
            learning=data["learning"],
            evidence=_evidence(data.get("evidence")),
            source=data["source"],
            created=as_date(data["created"], "created"),
            freshness=Freshness(data["freshness"]),
            confidence=float(data.get("confidence", 0.8)),
            recheck_on=as_opt_date(data.get("recheck_on"), "recheck_on"),
            status=RecordStatus(data.get("status", "active")),
            generalises=data.get("generalises", ""),
            contradicts=as_tuple(data.get("contradicts")),
            related_tasks=as_tuple(data.get("related_tasks")),
            related_commits=as_tuple(data.get("related_commits")),
            revalidation_reason=data.get("revalidation_reason", ""),
        )


@dataclass(frozen=True)
class FailureLearning:
    """What broke, why it broke, and what would catch it next time.

    Constitution rule 14: a failure that produced no learning is the only kind
    that was wasted. `detection` and `prevention` are required for that reason -
    a postmortem that stops at the root cause has described the failure without
    changing the odds of the next one.
    """

    kind: ClassVar[str] = "failure_learning"

    id: str
    what_failed: str
    symptom: str
    root_cause: str
    detection: str  # how it was caught, and how it could be caught sooner
    prevention: str
    evidence: tuple[Evidence, ...]
    source: str
    created: dt.date
    freshness: Freshness = Freshness.SLOW_CHANGING
    recurrence_guard: str = ""  # test id or check that now fails if it recurs
    confidence: float = 0.9
    recheck_on: dt.date | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    contradicts: tuple[str, ...] = ()
    related_tasks: tuple[str, ...] = ()
    related_commits: tuple[str, ...] = ()
    revalidation_reason: str = ""

    def __post_init__(self) -> None:
        _assert_id(self.id, "failure_learning")
        assert_text(self.what_failed, "what_failed")
        assert_text(self.symptom, "symptom")
        assert_text(self.root_cause, "root_cause")
        assert_text(self.detection, "detection")
        assert_text(self.prevention, "prevention")
        assert_text(self.source, "failure source")
        _assert_confidence(self.confidence, "failure_learning")
        if not self.evidence:
            raise KnowledgeError(f"failure_learning {self.id!r}: evidence is required")
        if self.recheck_on is None:
            object.__setattr__(self, "recheck_on", default_recheck_on(self.freshness, self.created))

    @property
    def has_recurrence_guard(self) -> bool:
        return bool(self.recurrence_guard.strip())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailureLearning:
        return cls(
            id=data["id"],
            what_failed=data["what_failed"],
            symptom=data["symptom"],
            root_cause=data["root_cause"],
            detection=data["detection"],
            prevention=data["prevention"],
            evidence=_evidence(data.get("evidence")),
            source=data["source"],
            created=as_date(data["created"], "created"),
            freshness=Freshness(data.get("freshness", "slow_changing")),
            recurrence_guard=data.get("recurrence_guard", ""),
            confidence=float(data.get("confidence", 0.9)),
            recheck_on=as_opt_date(data.get("recheck_on"), "recheck_on"),
            status=RecordStatus(data.get("status", "active")),
            contradicts=as_tuple(data.get("contradicts")),
            related_tasks=as_tuple(data.get("related_tasks")),
            related_commits=as_tuple(data.get("related_commits")),
            revalidation_reason=data.get("revalidation_reason", ""),
        )


KnowledgeRecord = Fact | Hypothesis | Decision | ExperimentLearning | FailureLearning

RECORD_TYPES: dict[str, type] = {
    Fact.kind: Fact,
    Hypothesis.kind: Hypothesis,
    Decision.kind: Decision,
    ExperimentLearning.kind: ExperimentLearning,
    FailureLearning.kind: FailureLearning,
}

# The types that carry a freshness class, and can therefore go stale.
DECAYING_TYPES: tuple[type, ...] = (Fact, ExperimentLearning, FailureLearning)


def promote(
    hypothesis: Hypothesis,
    *,
    evidence: tuple[Evidence, ...],
    freshness: Freshness,
    created: dt.date,
    source: str,
    fact_id: str = "",
    confidence: float = 1.0,
    statement: str = "",
) -> Fact:
    """Turn a supported hypothesis into a fact. The only route between them.

    Both preconditions are load-bearing. A hypothesis that is still `OPEN` has
    not earned promotion; one promoted without evidence would be a guess
    wearing a fact's shape, which is exactly what rule 16 exists to prevent.

    The hypothesis is not modified - it stays in the store as the record of
    where the fact came from, and the fact points back at it via `derived_from`.
    """
    if hypothesis.status is not HypothesisStatus.SUPPORTED:
        raise KnowledgeError(
            f"hypothesis {hypothesis.id!r} is {hypothesis.status.value}; only a "
            "supported hypothesis may be promoted to a fact"
        )
    if not evidence:
        raise KnowledgeError(
            f"hypothesis {hypothesis.id!r}: promotion requires evidence - that is the "
            "entire difference between a fact and a hypothesis"
        )
    return Fact(
        id=fact_id or f"{hypothesis.id}-fact",
        statement=statement or hypothesis.statement,
        evidence=tuple(evidence),
        source=source,
        created=created,
        freshness=freshness,
        confidence=confidence,
        related_tasks=hypothesis.related_tasks,
        related_experiments=hypothesis.related_experiments,
        related_commits=hypothesis.related_commits,
        derived_from=hypothesis.id,
    )


def flag_for_revalidation(record: Any, reason: str) -> Any:
    """Mark a decaying record as needing a recheck, keeping every other field.

    Flagging a `PERMANENT` record is refused on purpose: if an invariant turns
    out to be revalidatable, the mistake was the class, and the fix is a new
    record that supersedes it rather than a status change that hides it.
    """
    if not isinstance(record, DECAYING_TYPES):
        raise KnowledgeError(
            f"{type(record).__name__} carries no freshness class and cannot be "
            "flagged for revalidation"
        )
    if record.freshness is Freshness.PERMANENT:
        raise KnowledgeError(
            f"{record.id!r} is marked permanent. If it needs revalidation the class "
            "was wrong - supersede it with a correctly classified record."
        )
    assert_text(reason, "revalidation reason")
    return replace(record, status=RecordStatus.NEEDS_REVALIDATION, revalidation_reason=reason)

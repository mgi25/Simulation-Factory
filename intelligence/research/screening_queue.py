"""The order to screen in, built only from numbers a researcher actually typed.

Three hundred candidates and one afternoon is an ordering problem, and it is the
exact place a research system grows a model. This one does not. A researcher
scores a candidate on five named signals, each score carries a reason, and this
module sorts what they supplied. There is no term-frequency heuristic, no view
threshold, no recency bonus and no weighting - nothing here reads a candidate's
public metrics at all, which is the same refusal `scoring.py` makes for
opportunities and for the same reason: "higher views is a better candidate" is
not a rule somebody forgot to write, it is a rule with no input to write it from.

    ScreeningAssessment   one reviewer's signals for one candidate, with reasons
    QueueEntry            one row of the ordered queue, with its own coverage
    ScreeningCoverage     how much of the batch anybody has actually looked at

## An assessment is not a decision

Nothing in this module changes a candidate's state. `ScreeningRecommendation`
is what a reviewer thinks; `discovery.screen_candidate` is what the queue does,
and it still takes a person, a date and a reason of its own. The separation is
deliberate: a recommendation recorded today and acted on next week should leave
two rows, because the interesting question six weeks later is whether the person
who decided saw what the person who recommended saw.

## Coverage beats totals, so the ordering uses the mean

A total rewards whoever filled in more boxes: four fours beat three fives. So
entries are ordered by the *mean* of the signals they supplied, and - the part
that matters - a partially scored candidate never sorts above a fully scored
one, whatever its mean. Coverage is a fact about the assessment, not a penalty
applied to the candidate, and keeping the two groups apart is how the gap stays
visible instead of being averaged away. `ScoreResult.is_comparable` draws the
same line with the same argument.

## Unscored is a place in the queue, not an omission

A candidate nobody has assessed appears at the bottom with `UNSCORED`, and so
does one whose assessment carries a reason and no scores. Dropping either would
make the queue shorter and the batch's screening coverage invisible, which is
the one number that says whether the ordering means anything yet.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Iterable

from ai_platform.serde import as_date
from intelligence.research.common import (
    Evidence,
    assert_nonempty,
    assert_research_id,
    assert_text,
    evidence_tuple,
)
from intelligence.research.discovery import CandidateState
from intelligence.research.errors import ResearchError
from intelligence.research.scoring import DimensionScore

SCREENING_SIGNALS: tuple[str, ...] = (
    "relevance",
    "novelty_potential",
    "format_family_potential",
    "channel_fit",
    "evidence_completeness",
)
"""The five signals a screener may score, and the whole vocabulary.

Fixed rather than open, because these are counted and compared across a batch
and a free vocabulary makes coverage uncomputable - the same argument
`assert_slug` makes for tags. Adding a sixth signal is a one-line change here;
every existing assessment stays valid and becomes *incomplete*, which is the
honest consequence and the reason the change is not free.
"""

QUEUE_CAVEAT = (
    "An ordering of researcher judgement. The mean is unweighted and is not "
    "evidence, not confidence and not a decision; read the per-signal reasons "
    "before spending an afternoon on anything in this list."
)


class ScreeningRecommendation(Enum):
    """What the reviewer thinks. Not what the queue has done about it."""

    SCREEN_IN = "screen_in"
    SCREEN_OUT = "screen_out"
    NEEDS_REVIEW = "needs_review"


class QueueStatus(Enum):
    SCORED = "scored"
    PARTIALLY_SCORED = "partially_scored"
    UNSCORED = "unscored"


_STATUS_ORDER: dict[QueueStatus, int] = {
    QueueStatus.SCORED: 0,
    QueueStatus.PARTIALLY_SCORED: 1,
    QueueStatus.UNSCORED: 2,
}

# States where a screening decision is still ahead of the candidate. Everything
# else has already been decided, and ordering a decided candidate against an
# undecided one would suggest the decision is up for grabs.
OPEN_STATES: frozenset[CandidateState] = frozenset(
    {
        CandidateState.DISCOVERED,
        CandidateState.QUEUED,
        CandidateState.SCREENED_IN,
    }
)


@dataclass(frozen=True)
class ScreeningAssessment:
    """One reviewer's screening signals for one candidate, in one batch.

    `reason` and `evidence` are required whether or not any signal was scored.
    A screening judgement with neither is an opinion with a date on it, and
    constitution rule 7 asks important claims to identify their evidence - a
    judgement that sends a video to an analyst's afternoon, or away from one, is
    an important claim.
    """

    kind: ClassVar[str] = "screening_assessment"

    id: str
    batch_id: str
    candidate_id: str
    reviewer: str
    reviewed_on: dt.date
    reason: str
    evidence: tuple[Evidence, ...]
    scores: tuple[DimensionScore, ...] = ()
    scale_max: int = 5
    recommendation: ScreeningRecommendation = ScreeningRecommendation.NEEDS_REVIEW
    note: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "screening assessment")
        assert_research_id(self.batch_id, "research batch")
        assert_research_id(self.candidate_id, "discovery candidate")
        assert_text(self.reviewer, "screening reviewer (who looked at this)")
        assert_text(self.reason, "screening reason (why, in one sentence)")
        if not isinstance(self.reviewed_on, dt.date):
            raise ResearchError("a screening assessment must record the day it was made")
        if not isinstance(self.recommendation, ScreeningRecommendation):
            raise ResearchError(
                f"assessment {self.id!r}: recommendation must be a ScreeningRecommendation"
            )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        assert_nonempty(
            self.evidence,
            "evidence",
            "a screening judgement without something a reader can check is an opinion "
            "with a date on it (constitution rule 7)",
        )

        if isinstance(self.scale_max, bool) or not isinstance(self.scale_max, int):
            raise ResearchError(f"assessment {self.id!r}: scale_max must be a whole number")
        if self.scale_max < 2:
            raise ResearchError(
                f"assessment {self.id!r}: scale_max {self.scale_max} leaves nothing to score"
            )

        scores = tuple(self.scores)
        for score in scores:
            if not isinstance(score, DimensionScore):
                raise ResearchError(
                    f"assessment {self.id!r}: a screening signal is a DimensionScore - a "
                    "number and the reason for it"
                )
            if score.dimension not in SCREENING_SIGNALS:
                raise ResearchError(
                    f"assessment {self.id!r} scores {score.dimension!r}, which is not a "
                    f"screening signal. The vocabulary is {', '.join(SCREENING_SIGNALS)}; "
                    "a signal nobody else scores cannot be compared across the batch."
                )
            if score.score > self.scale_max:
                raise ResearchError(
                    f"assessment {self.id!r}: {score.dimension} scored {score.score} on a "
                    f"scale that stops at {self.scale_max}"
                )
        names = [score.dimension for score in scores]
        if len(set(names)) != len(names):
            raise ResearchError(
                f"assessment {self.id!r}: a signal is scored twice. One of the two would "
                "silently win the mean."
            )
        object.__setattr__(self, "scores", scores)

    @property
    def scored_signals(self) -> tuple[str, ...]:
        """In the declared signal order, so two assessments read the same way."""
        scored = {score.dimension for score in self.scores}
        return tuple(name for name in SCREENING_SIGNALS if name in scored)

    @property
    def missing_signals(self) -> tuple[str, ...]:
        scored = {score.dimension for score in self.scores}
        return tuple(name for name in SCREENING_SIGNALS if name not in scored)

    @property
    def coverage(self) -> float:
        return round(len(self.scores) / len(SCREENING_SIGNALS), 6)

    @property
    def is_complete(self) -> bool:
        return not self.missing_signals

    @property
    def signal_total(self) -> int | None:
        """The sum of what was scored. `None` when nothing was."""
        return sum(score.score for score in self.scores) if self.scores else None

    @property
    def signal_mean(self) -> float | None:
        """Unweighted, over the signals supplied. `None` when none were.

        Unweighted on purpose: a weighting is a decision about what matters, and
        a decision nobody wrote down is a model hiding in an ordering.
        """
        if not self.scores:
            return None
        return round(sum(score.score for score in self.scores) / len(self.scores), 6)

    def by_signal(self) -> dict[str, DimensionScore]:
        return {score.dimension: score for score in self.scores}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreeningAssessment:
        return cls(
            id=data["id"],
            batch_id=data["batch_id"],
            candidate_id=data["candidate_id"],
            reviewer=data["reviewer"],
            reviewed_on=as_date(data["reviewed_on"], "reviewed_on"),
            reason=data["reason"],
            evidence=evidence_tuple(data.get("evidence")),
            scores=tuple(DimensionScore.from_dict(s) for s in data.get("scores", ())),
            scale_max=data.get("scale_max", 5),
            recommendation=ScreeningRecommendation(
                data.get("recommendation", "needs_review")
            ),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class QueueEntry:
    """One row of the screening queue, carrying its own coverage.

    `assessed` and `status` are separate because "nobody has looked at this" and
    "somebody looked and scored nothing" are different facts about a candidate,
    and only the first one is a gap in the batch's screening coverage.
    """

    candidate_id: str
    state: CandidateState
    status: QueueStatus
    assessed: bool
    assessment_id: str = ""
    reviewer: str = ""
    reviewed_on: dt.date | None = None
    recommendation: ScreeningRecommendation = ScreeningRecommendation.NEEDS_REVIEW
    signal_total: int | None = None
    signal_mean: float | None = None
    scored_signals: tuple[str, ...] = ()
    missing_signals: tuple[str, ...] = SCREENING_SIGNALS
    coverage: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.status is QueueStatus.SCORED


def assess(
    candidate_id: str,
    assessments: Iterable[ScreeningAssessment],
) -> ScreeningAssessment | None:
    """The assessment for one candidate: the latest, ties broken by id.

    A candidate reviewed twice keeps both records - the store never overwrites -
    and the queue reads the later one. Two on the same day order by id, so the
    queue is the same list on every machine.
    """
    found = [a for a in assessments if a.candidate_id == candidate_id]
    if not found:
        return None
    found.sort(key=lambda a: (a.reviewed_on, a.id))
    return found[-1]


def _entry(
    candidate_id: str,
    state: CandidateState,
    assessment: ScreeningAssessment | None,
) -> QueueEntry:
    if assessment is None:
        return QueueEntry(
            candidate_id=candidate_id,
            state=state,
            status=QueueStatus.UNSCORED,
            assessed=False,
        )
    if not assessment.scores:
        status = QueueStatus.UNSCORED
    elif assessment.is_complete:
        status = QueueStatus.SCORED
    else:
        status = QueueStatus.PARTIALLY_SCORED
    return QueueEntry(
        candidate_id=candidate_id,
        state=state,
        status=status,
        assessed=True,
        assessment_id=assessment.id,
        reviewer=assessment.reviewer,
        reviewed_on=assessment.reviewed_on,
        recommendation=assessment.recommendation,
        signal_total=assessment.signal_total,
        signal_mean=assessment.signal_mean,
        scored_signals=assessment.scored_signals,
        missing_signals=assessment.missing_signals,
        coverage=assessment.coverage,
    )


def screening_queue(
    candidates: Iterable[tuple[str, CandidateState]],
    assessments: Iterable[ScreeningAssessment],
    *,
    states: frozenset[CandidateState] = OPEN_STATES,
) -> tuple[QueueEntry, ...]:
    """Order the candidates still awaiting a decision. Pure, and deterministic.

    Sorted by `(status, -mean, candidate_id)`: fully scored first, then
    partially scored, then unscored, and inside each group by the mean of the
    signals a reviewer supplied. The id tiebreak is what makes a printed queue
    reviewable - two candidates with identical signals come back in the same
    order in every process, on every machine.

    Nothing is dropped except candidates whose screening decision has already
    been made; `ScreeningCoverage` counts over the whole batch, so a filtered
    queue never hides how little of it has been looked at.
    """
    stored = tuple(assessments)
    rows = [
        _entry(candidate_id, state, assess(candidate_id, stored))
        for candidate_id, state in candidates
        if state in states
    ]
    rows.sort(
        key=lambda entry: (
            _STATUS_ORDER[entry.status],
            -(entry.signal_mean if entry.signal_mean is not None else 0.0),
            entry.candidate_id,
        )
    )
    return tuple(rows)


@dataclass(frozen=True)
class ScreeningCoverage:
    """How much of a batch anybody has actually looked at.

    The number that says whether the queue's ordering means anything yet: an
    ordering over the eleven candidates somebody scored, out of ninety, is an
    ordering of eleven candidates and the report says so.
    """

    candidates: int
    assessed: int
    unassessed: int
    fully_scored: int
    partially_scored: int
    unscored: int
    signal_coverage: tuple[tuple[str, int], ...] = ()
    mean_coverage: float | None = None
    reviewers: tuple[str, ...] = ()
    recommendations: tuple[tuple[str, int], ...] = ()

    @property
    def assessed_fraction(self) -> float | None:
        if not self.candidates:
            return None
        return round(self.assessed / self.candidates, 6)


def screening_coverage(
    candidates: Iterable[tuple[str, CandidateState]],
    assessments: Iterable[ScreeningAssessment],
) -> ScreeningCoverage:
    """Count assessments over *every* candidate in the batch, decided or not. Pure."""
    stored = tuple(assessments)
    rows = tuple(candidates)
    entries = [_entry(cid, state, assess(cid, stored)) for cid, state in rows]

    per_signal = {name: 0 for name in SCREENING_SIGNALS}
    for entry in entries:
        for name in entry.scored_signals:
            per_signal[name] += 1

    recommendations = {value.value: 0 for value in ScreeningRecommendation}
    for entry in entries:
        if entry.assessed:
            recommendations[entry.recommendation.value] += 1

    assessed = [entry for entry in entries if entry.assessed]
    mean_coverage = (
        round(sum(entry.coverage for entry in assessed) / len(assessed), 6)
        if assessed
        else None
    )
    return ScreeningCoverage(
        candidates=len(entries),
        assessed=len(assessed),
        unassessed=len(entries) - len(assessed),
        fully_scored=sum(1 for e in entries if e.status is QueueStatus.SCORED),
        partially_scored=sum(
            1 for e in entries if e.status is QueueStatus.PARTIALLY_SCORED
        ),
        unscored=sum(1 for e in entries if e.status is QueueStatus.UNSCORED),
        signal_coverage=tuple((name, per_signal[name]) for name in SCREENING_SIGNALS),
        mean_coverage=mean_coverage,
        reviewers=tuple(sorted({entry.reviewer for entry in assessed})),
        recommendations=tuple(
            (name, recommendations[name]) for name in sorted(recommendations)
        ),
    )
